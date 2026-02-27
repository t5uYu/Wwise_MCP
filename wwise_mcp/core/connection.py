"""
WAAPI 连接管理 — 基于官方 waapi-client 库
WaapiClient 内部封装了完整的 WAMP 协议，无需手写协议细节。
"""

import asyncio
import logging
from typing import Optional

from waapi import WaapiClient
from waapi.wamp.interface import CannotConnectToWaapiException

from ..config import settings
from .exceptions import WwiseConnectionError, WwiseAPIError

logger = logging.getLogger("wwise_mcp.connection")


class WwiseConnection:
    """
    对 WaapiClient 的薄封装，提供 async 接口供 WwiseAdapter 使用。
    WaapiClient 本身是同步阻塞调用，通过 asyncio.to_thread() 避免阻塞事件循环。
    """

    def __init__(self):
        self._client: Optional[WaapiClient] = None

    async def ensure_connected(self) -> None:
        """确保连接可用，未连接时主动建立连接。"""
        if self._client and self._client.is_connected():
            return
        await self._connect()

    async def _connect(self) -> None:
        try:
            self._client = await asyncio.to_thread(
                lambda: WaapiClient(settings.waapi_url)
            )
            logger.info("WAAPI 连接成功：%s", settings.waapi_url)
        except CannotConnectToWaapiException as e:
            raise WwiseConnectionError(str(e))
        except Exception as e:
            raise WwiseConnectionError(f"连接失败：{e}")

    async def call(self, uri: str, payload: dict) -> dict:
        """
        发送 WAAPI 调用。超时时自动重试一次（设计方案错误处理策略）。
        payload 是 arguments + options 合并后的完整字典，由 WwiseAdapter 负责组装。
        """
        if not self._client or not self._client.is_connected():
            await self.ensure_connected()

        for attempt in range(2):  # 最多尝试 2 次（1 次重试）
            try:
                result = await asyncio.to_thread(
                    lambda: self._client.call(uri, payload)
                )
                if result is None:
                    raise WwiseAPIError(
                        f"WAAPI 调用 '{uri}' 返回 None（参数可能有误，请检查 Wwise 日志）"
                    )
                return result
            except WwiseAPIError:
                raise
            except asyncio.TimeoutError:
                if attempt == 0:
                    logger.warning("WAAPI 调用 '%s' 超时，正在重试…", uri)
                    continue
                from .exceptions import WwiseTimeoutError
                raise WwiseTimeoutError()
            except Exception as e:
                raise WwiseAPIError(f"WAAPI 调用 '{uri}' 异常：{e}")

    async def close(self) -> None:
        """断开连接，释放资源。"""
        if self._client:
            await asyncio.to_thread(self._client.disconnect)
            self._client = None
