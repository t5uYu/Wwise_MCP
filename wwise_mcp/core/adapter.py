"""
WwiseAdapter：Layer 1 — WAAPI Host Adapter
封装所有 WAAPI 调用，对上层工具暴露简洁接口。
"""

import logging
from typing import Any, Callable, Optional

from .connection import WwiseConnection
from .exceptions import WwiseAPIError, WwiseConnectionError

logger = logging.getLogger("wwise_mcp.adapter")

# 全局共享连接实例（在 server.py 的 lifespan 中初始化）
_connection: Optional[WwiseConnection] = None


def get_connection() -> WwiseConnection:
    """获取全局 WAAPI 连接实例"""
    if _connection is None:
        raise WwiseConnectionError("WwiseAdapter 尚未初始化，请确认 MCP Server 已正常启动")
    return _connection


def init_connection() -> WwiseConnection:
    """初始化全局连接实例（在 server lifespan 中调用）"""
    global _connection
    _connection = WwiseConnection()
    return _connection


class WwiseAdapter:
    """
    WAAPI 调用封装。
    每个工具函数通过此类访问 Wwise，不直接操作 WebSocket。
    """

    def __init__(self, connection: Optional[WwiseConnection] = None):
        self._conn = connection or get_connection()

    # ------------------------------------------------------------------
    # 核心调用接口
    # ------------------------------------------------------------------

    async def call(self, uri: str, args: dict = {}, opts: dict = {}) -> dict:
        """
        执行 WAAPI JSON-RPC 调用。

        Args:
            uri:  WAAPI 函数 URI，如 'ak.wwise.core.object.get'
            args: 业务参数（对应 WAAPI 的 arguments 字段）
            opts: 返回字段控制（对应 WAAPI 的 options 字段）

        Returns:
            WAAPI 返回的 result 字典

        Raises:
            WwiseAPIError: Wwise 返回了业务错误
            WwiseConnectionError: 连接不可用
            WwiseTimeoutError: 请求超时
        """
        try:
            result = await self._conn.call(uri, args, opts)
            return result
        except WwiseAPIError:
            raise
        except Exception as e:
            # 将原始 WebSocket/asyncio 异常转为 WwiseAPIError
            error_msg = str(e)
            if "not found" in error_msg.lower() or "does not exist" in error_msg.lower():
                raise WwiseAPIError(error_msg)
            raise WwiseAPIError(f"WAAPI 调用 '{uri}' 失败：{error_msg}")

    async def subscribe(self, uri: str, callback: Callable) -> int:
        """
        订阅 WAAPI 事件通知。

        Returns:
            subscription_id，用于后续 unsubscribe
        """
        return await self._conn.subscribe(uri, callback)

    async def unsubscribe(self, subscription_id: int) -> None:
        """取消订阅"""
        await self._conn.unsubscribe(subscription_id)

    # ------------------------------------------------------------------
    # 便利方法：常用 WAAPI 调用的高级封装
    # ------------------------------------------------------------------

    async def get_info(self) -> dict:
        """获取 Wwise 项目基础信息"""
        return await self.call("ak.wwise.core.getInfo")

    async def get_objects(
        self,
        from_spec: dict,
        return_fields: list[str] | None = None,
        transform: list | None = None,
    ) -> list[dict]:
        """
        通用对象查询。

        Args:
            from_spec:     WAAPI from 选择器，如 {"path": "\\Actor-Mixer Hierarchy"}
            return_fields: 需要返回的字段列表，如 ["@name", "@type", "@path"]
            transform:     WAAPI transform 管线（排序、过滤等）

        Returns:
            对象列表
        """
        if return_fields is None:
            return_fields = ["@name", "@type", "@path", "@id"]

        args: dict[str, Any] = {"from": from_spec}
        if transform:
            args["transform"] = transform

        opts = {"return": return_fields}
        result = await self.call("ak.wwise.core.object.get", args, opts)
        return result.get("return", [])

    async def create_object(
        self,
        name: str,
        obj_type: str,
        parent_path: str,
        on_conflict: str = "rename",
        children: list | None = None,
        notes: str = "",
    ) -> dict:
        """创建 Wwise 对象"""
        args: dict[str, Any] = {
            "name": name,
            "type": obj_type,
            "parent": {"path": parent_path},
            "onNameConflict": on_conflict,
        }
        if children:
            args["children"] = children
        if notes:
            args["notes"] = notes

        result = await self.call("ak.wwise.core.object.create", args)
        return result

    async def set_property(
        self, object_path: str, prop: str, value: Any, platform: str | None = None
    ) -> dict:
        """设置对象属性（数值/布尔类属性）"""
        args: dict[str, Any] = {
            "object": {"path": object_path},
            "property": prop,
            "value": value,
        }
        if platform:
            args["platform"] = platform
        return await self.call("ak.wwise.core.object.setProperty", args)

    async def set_reference(
        self, object_path: str, reference: str, value_path: str, platform: str | None = None
    ) -> dict:
        """设置对象引用（OutputBus、Effect 等引用类属性）"""
        args: dict[str, Any] = {
            "object": {"path": object_path},
            "reference": reference,
            "value": {"path": value_path},
        }
        if platform:
            args["platform"] = platform
        return await self.call("ak.wwise.core.object.setReference", args)

    async def delete_object(self, object_path: str) -> dict:
        """删除对象"""
        return await self.call(
            "ak.wwise.core.object.delete",
            {"object": {"path": object_path}},
        )

    async def move_object(self, object_path: str, new_parent_path: str) -> dict:
        """移动对象到新父节点"""
        return await self.call(
            "ak.wwise.core.object.move",
            {
                "object": {"path": object_path},
                "parent": {"path": new_parent_path},
                "onNameConflict": "rename",
            },
        )

    async def get_selected_objects(self) -> list[dict]:
        """获取 Wwise 编辑器中当前选中的对象"""
        result = await self.call(
            "ak.wwise.ui.getSelectedObjects",
            {},
            {"return": ["@name", "@type", "@path", "@id"]},
        )
        return result.get("objects", [])
