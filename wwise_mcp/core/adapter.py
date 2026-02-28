"""
WwiseAdapter：Layer 1 — WAAPI Host Adapter
封装所有 WAAPI 调用，对上层工具暴露简洁接口。
"""

import logging
from typing import Any, Optional

from .connection import WwiseConnection
from .exceptions import WwiseAPIError, WwiseConnectionError

logger = logging.getLogger("wwise_mcp.adapter")

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
    每个工具函数通过此类访问 Wwise，不直接操作底层连接。

    调用约定：
      - args: WAAPI arguments 字典（from/name/type 等业务参数）
      - opts: WAAPI options 字典（return 字段等），内部合并为 {"options": opts}
      - 返回字段名不带 @ 前缀（name/path/id/type/childrenCount 等）
    """

    def __init__(self, connection: Optional[WwiseConnection] = None):
        self._conn = connection or get_connection()

    # ------------------------------------------------------------------
    # 核心调用接口
    # ------------------------------------------------------------------

    async def call(self, uri: str, args: dict = {}, opts: dict = {}) -> dict:
        """
        执行 WAAPI 调用。

        Args:
            uri:  WAAPI 函数 URI，如 'ak.wwise.core.object.get'
            args: 业务参数字典
            opts: 返回字段控制，如 {"return": ["name", "path"]}
                  内部会合并为 {**args, "options": opts} 传给 waapi-client
        """
        payload = dict(args)
        if opts:
            payload["options"] = opts
        return await self._conn.call(uri, payload)

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
            from_spec:     WAAPI from 选择器，如 {"path": ["\\Actor-Mixer Hierarchy"]} 或 {"ofType": ["Sound"]}
            return_fields: 返回字段列表，不带 @ 前缀，如 ["name", "type", "path", "id"]
            transform:     WAAPI transform 管线（排序、过滤等）
        """
        if return_fields is None:
            return_fields = ["name", "type", "path", "id"]

        args: dict[str, Any] = {"from": from_spec}
        if transform:
            args["transform"] = transform

        result = await self.call(
            "ak.wwise.core.object.get",
            args,
            {"return": return_fields},
        )
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
            "parent": parent_path,
            "onNameConflict": on_conflict,
        }
        if children:
            args["children"] = children
        if notes:
            args["notes"] = notes
        result = await self.call("ak.wwise.core.object.create", args)
        # object.create 不支持 options.return，不返回 path；
        # 用返回的 id 额外查一次以获取 path（FIXES_3 已记录此限制）
        obj_id = result.get("id") if result else None
        if obj_id:
            try:
                objs = await self.get_objects(
                    from_spec={"id": [obj_id]},
                    return_fields=["name", "path", "type"],
                )
                if objs:
                    result = {**result, "path": objs[0].get("path"), "name": objs[0].get("name")}
            except Exception:
                pass
        return result

    async def set_property(
        self, object_path: str, prop: str, value: Any, platform: str | None = None
    ) -> dict:
        """设置对象属性（数值/布尔类属性）"""
        args: dict[str, Any] = {
            "object": object_path,
            "property": prop,
            "value": value,
        }
        if platform:
            args["platform"] = platform
        return await self.call("ak.wwise.core.object.setProperty", args)

    async def set_reference(
        self, object_path: str, reference: str, value_path: str, platform: str | None = None
    ) -> dict:
        """设置对象引用（OutputBus、Target 等引用类属性）"""
        args: dict[str, Any] = {
            "object": object_path,
            "reference": reference,
            "value": value_path,
        }
        if platform:
            args["platform"] = platform
        return await self.call("ak.wwise.core.object.setReference", args)

    async def delete_object(self, object_path: str) -> dict:
        """删除对象"""
        return await self.call(
            "ak.wwise.core.object.delete",
            {"object": object_path},
        )

    async def move_object(self, object_path: str, new_parent_path: str) -> dict:
        """移动对象到新父节点"""
        return await self.call(
            "ak.wwise.core.object.move",
            {
                "object": object_path,
                "parent": new_parent_path,
                "onNameConflict": "rename",
            },
        )

    async def get_selected_objects(self) -> list[dict]:
        """获取 Wwise 编辑器中当前选中的对象"""
        result = await self.call(
            "ak.wwise.ui.getSelectedObjects",
            {},
            {"return": ["name", "type", "path", "id"]},
        )
        return result.get("objects", [])
