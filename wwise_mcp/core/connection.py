"""
WAAPI WebSocket 连接管理
负责：持久连接维护、断线自动重连、订阅生命周期管理
"""

import asyncio
import json
import logging
import time
from typing import Any, Callable, Dict, Optional

import websockets
from websockets.exceptions import ConnectionClosed, WebSocketException

from ..config import settings
from .exceptions import WwiseConnectionError, WwiseTimeoutError

logger = logging.getLogger("wwise_mcp.connection")


class WwiseConnection:
    """
    单个 WAAPI WebSocket 连接的生命周期管理。
    - 负责持久连接维护和断线重连
    - 管理 JSON-RPC 请求/响应的 ID 匹配
    - 管理订阅回调的生命周期
    """

    def __init__(self):
        self._ws: Optional[websockets.WebSocketClientProtocol] = None
        self._lock = asyncio.Lock()
        self._pending: Dict[int, asyncio.Future] = {}   # request_id -> Future
        self._subscriptions: Dict[int, Callable] = {}   # subscription_id -> callback
        self._request_id: int = 0
        self._subscription_id: int = 0
        self._listener_task: Optional[asyncio.Task] = None
        self._connected = False

    # ------------------------------------------------------------------
    # 公开接口
    # ------------------------------------------------------------------

    async def ensure_connected(self) -> None:
        """确保连接可用，必要时执行重连"""
        if self._connected and self._ws and not self._ws.closed:
            return
        await self._connect_with_retry()

    async def call(self, uri: str, args: dict = {}, opts: dict = {}) -> dict:
        """
        发送 WAAPI JSON-RPC 请求并等待响应。
        如连接不可用，先触发重连。
        """
        await self.ensure_connected()

        request_id = self._next_request_id()
        payload = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": uri,
            "params": {
                "arguments": args,
                "options": opts,
            },
        }

        loop = asyncio.get_event_loop()
        future: asyncio.Future = loop.create_future()
        self._pending[request_id] = future

        try:
            await asyncio.wait_for(
                self._ws.send(json.dumps(payload)),
                timeout=settings.timeout,
            )
            result = await asyncio.wait_for(future, timeout=settings.timeout)
            return result
        except asyncio.TimeoutError:
            self._pending.pop(request_id, None)
            raise WwiseTimeoutError()
        except (ConnectionClosed, WebSocketException):
            self._pending.pop(request_id, None)
            self._connected = False
            raise WwiseConnectionError("WAAPI 连接在请求过程中断开")

    async def subscribe(self, uri: str, callback: Callable) -> int:
        """
        订阅 WAAPI 事件。
        返回 subscription_id，可通过 unsubscribe() 取消。
        """
        await self.ensure_connected()

        sub_id = self._next_subscription_id()
        request_id = self._next_request_id()

        payload = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": uri,
            "params": {"arguments": {}, "options": {}},
        }

        loop = asyncio.get_event_loop()
        future: asyncio.Future = loop.create_future()
        self._pending[request_id] = future

        await self._ws.send(json.dumps(payload))
        result = await asyncio.wait_for(future, timeout=settings.timeout)

        # Wwise WAAPI 订阅成功后，后续推送消息带相同 subscription id
        waapi_sub_id = result.get("id", sub_id)
        self._subscriptions[waapi_sub_id] = callback
        return waapi_sub_id

    async def unsubscribe(self, subscription_id: int) -> None:
        """取消订阅"""
        self._subscriptions.pop(subscription_id, None)

    async def close(self) -> None:
        """关闭连接，清理资源"""
        self._connected = False
        if self._listener_task and not self._listener_task.done():
            self._listener_task.cancel()
        if self._ws and not self._ws.closed:
            await self._ws.close()

    # ------------------------------------------------------------------
    # 内部实现
    # ------------------------------------------------------------------

    async def _connect_with_retry(self) -> None:
        """带指数退避的重连逻辑"""
        last_error = None
        for attempt in range(1, settings.max_reconnect + 1):
            try:
                logger.info("尝试连接 WAAPI %s（第 %d 次）", settings.waapi_url, attempt)
                self._ws = await asyncio.wait_for(
                    websockets.connect(
                        settings.waapi_url,
                        max_size=16 * 1024 * 1024,  # 16MB，应对大型项目响应
                        ping_interval=20,
                        ping_timeout=10,
                    ),
                    timeout=settings.timeout,
                )
                self._connected = True
                # 启动后台消息监听协程
                self._listener_task = asyncio.create_task(self._listen())
                logger.info("WAAPI 连接成功")
                return
            except Exception as e:
                last_error = e
                logger.warning("连接失败（%s），%.1f 秒后重试…", e, settings.reconnect_interval)
                if attempt < settings.max_reconnect:
                    await asyncio.sleep(settings.reconnect_interval)

        raise WwiseConnectionError(
            f"连接 WAAPI 失败（已重试 {settings.max_reconnect} 次）：{last_error}"
        )

    async def _listen(self) -> None:
        """后台消息监听循环，将收到的消息路由到对应 Future 或订阅回调"""
        try:
            async for raw in self._ws:
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    logger.warning("收到非 JSON 消息：%s", raw[:200])
                    continue

                msg_id = msg.get("id")

                # 区分：正常 RPC 响应 vs 订阅推送
                if msg_id in self._pending:
                    future = self._pending.pop(msg_id)
                    if "error" in msg:
                        future.set_exception(
                            Exception(msg["error"].get("message", "WAAPI 错误"))
                        )
                    else:
                        future.set_result(msg.get("result", {}))
                elif msg_id in self._subscriptions:
                    callback = self._subscriptions[msg_id]
                    try:
                        asyncio.create_task(callback(msg.get("result", {})))
                    except Exception as e:
                        logger.error("订阅回调异常：%s", e)

        except (ConnectionClosed, WebSocketException):
            logger.warning("WAAPI 连接已关闭")
            self._connected = False
            # 唤醒所有等待中的 Future，注入连接错误
            for future in self._pending.values():
                if not future.done():
                    future.set_exception(WwiseConnectionError())
            self._pending.clear()

    def _next_request_id(self) -> int:
        self._request_id += 1
        return self._request_id

    def _next_subscription_id(self) -> int:
        self._subscription_id += 1
        return self._subscription_id
