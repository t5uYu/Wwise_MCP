"""
WwiseMCP Server 入口
FastMCP 实例化 + 17 个工具注册 + 生命周期管理

启动方式：
  python -m wwise_mcp.server          # stdio 模式（Cursor / Claude Desktop）
  python -m wwise_mcp.server --sse    # SSE 模式
"""

import asyncio
import logging
import os
import sys
from contextlib import asynccontextmanager
from typing import Any

from fastmcp import FastMCP

from .config import settings
from .core import init_connection
from .prompts.system_prompt import STATIC_SYSTEM_PROMPT
from .rag.context_collector import build_dynamic_context
from .tools import (
    # Query
    get_project_hierarchy,
    get_object_properties,
    search_objects,
    get_bus_topology,
    get_event_actions,
    get_soundbank_info,
    get_rtpc_list,
    # Action
    create_object,
    set_property,
    create_event,
    assign_bus,
    delete_object,
    move_object,
    # Verify
    verify_structure,
    verify_event_completeness,
    # Fallback
    execute_waapi,
)

# 日志配置
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("wwise_mcp.server")


# ------------------------------------------------------------------
# FastMCP 实例化
# ------------------------------------------------------------------

mcp = FastMCP(
    name="WwiseMCP",
    instructions=STATIC_SYSTEM_PROMPT,
)


# ------------------------------------------------------------------
# 生命周期：建立 WAAPI 连接
# ------------------------------------------------------------------

# 在 server 启动时初始化连接
_connection_initialized = False

async def _ensure_connection():
    global _connection_initialized
    if not _connection_initialized:
        conn = init_connection()
        try:
            await conn.ensure_connected()
            logger.info("WAAPI 连接已建立：%s", settings.waapi_url)
        except Exception as e:
            logger.warning("WAAPI 初始连接失败（工具调用时将自动重试）：%s", e)
        _connection_initialized = True


# ------------------------------------------------------------------
# 工具注册（17 个）
# ------------------------------------------------------------------

# --- 查询类（7 个）---

@mcp.tool()
async def tool_get_project_hierarchy() -> dict:
    """
    获取 Wwise 项目顶层结构概览。
    返回各主要层级（Actor-Mixer、Master-Mixer、Events 等）的对象数量和类型。
    2024.1 注意：Auto-Defined SoundBank 场景下 SoundBanks 节点可能为空，属正常行为。
    """
    await _ensure_connection()
    return await get_project_hierarchy()


@mcp.tool()
async def tool_get_object_properties(
    object_path: str,
    page: int = 1,
    page_size: int = 30,
) -> dict:
    """
    获取指定 Wwise 对象的属性详情。

    Args:
        object_path: WAAPI 路径，如 '\\\\Actor-Mixer Hierarchy\\\\Default Work Unit\\\\MySFX'
        page:        分页页码（从 1 开始）
        page_size:   每页属性数量，默认 30
    """
    await _ensure_connection()
    return await get_object_properties(object_path, page, page_size)


@mcp.tool()
async def tool_search_objects(
    query: str,
    type_filter: str | None = None,
    max_results: int = 20,
) -> dict:
    """
    按关键词模糊搜索 Wwise 对象。

    Args:
        query:       搜索关键词（对象名称模糊匹配）
        type_filter: 可选类型过滤，如 'Sound SFX', 'Event', 'Bus', 'GameParameter'
        max_results: 最多返回结果数，默认 20
    """
    await _ensure_connection()
    return await search_objects(query, type_filter, max_results)


@mcp.tool()
async def tool_get_bus_topology() -> dict:
    """
    获取 Master-Mixer Hierarchy 中所有 Bus 的拓扑结构（混音路由架构）。
    """
    await _ensure_connection()
    return await get_bus_topology()


@mcp.tool()
async def tool_get_event_actions(event_path: str) -> dict:
    """
    获取指定 Event 下所有 Action 的详情（类型、Target 引用等）。

    Args:
        event_path: Event 对象的完整 WAAPI 路径
    """
    await _ensure_connection()
    return await get_event_actions(event_path)


@mcp.tool()
async def tool_get_soundbank_info(soundbank_name: str | None = None) -> dict:
    """
    获取 SoundBank 信息。

    Args:
        soundbank_name: 指定名称；为 None 时返回所有 SoundBank 概览。

    注意：Wwise 2024.1 默认开启 Auto-Defined SoundBank，通常无需手动管理。
    """
    await _ensure_connection()
    return await get_soundbank_info(soundbank_name)


@mcp.tool()
async def tool_get_rtpc_list(max_results: int = 50) -> dict:
    """
    获取项目中所有 Game Parameter（RTPC）列表，含名称、范围、默认值。

    Args:
        max_results: 最多返回数量，默认 50
    """
    await _ensure_connection()
    return await get_rtpc_list(max_results)


# --- 操作类（6 个）---

@mcp.tool()
async def tool_create_object(
    name: str,
    obj_type: str,
    parent_path: str,
    on_conflict: str = "rename",
    notes: str = "",
) -> dict:
    """
    在指定父节点下创建 Wwise 对象。

    Args:
        name:        新对象名称
        obj_type:    类型：'Sound SFX' | 'Event' | 'Bus' | 'BlendContainer' | 'Action' 等
        parent_path: 父对象的完整 WAAPI 路径
        on_conflict: 名称冲突处理：'rename'（默认）| 'replace' | 'fail'
        notes:       备注（可选）
    """
    await _ensure_connection()
    return await create_object(name, obj_type, parent_path, on_conflict, notes)


@mcp.tool()
async def tool_set_property(
    object_path: str,
    property: str | None = None,
    value: Any = None,
    properties: dict | None = None,
    platform: str | None = None,
) -> dict:
    """
    设置对象的一个或多个属性。

    Args:
        object_path: 目标对象路径
        property:    单个属性名，如 'Volume', 'Pitch', 'LowPassFilter'
        value:       单个属性值（与 property 配合使用）
        properties:  批量属性字典，如 {"Volume": -6.0, "Pitch": 200}（推荐，减少调用次数）
        platform:    目标平台（None 表示所有平台）
    """
    await _ensure_connection()
    return await set_property(object_path, property, value, properties, platform)


@mcp.tool()
async def tool_create_event(
    event_name: str,
    action_type: str,
    target_path: str,
    parent_path: str = "\\Events\\Default Work Unit",
) -> dict:
    """
    创建 Wwise Event 及其 Action（自动完成三步操作：创建Event→创建Action→设置Target）。

    Args:
        event_name:  Event 名称，建议以动词开头，如 'Play_Explosion'
        action_type: 'Play' | 'Stop' | 'Pause' | 'Resume' | 'Break' | 'Mute' | 'UnMute'
        target_path: Action 目标对象路径（Sound/Container 等）
        parent_path: Event 父节点路径，默认 Default Work Unit

    2024.1 特性：创建后无需生成 SoundBank 即可通过 Live Editing 即时验证。
    """
    await _ensure_connection()
    return await create_event(event_name, action_type, target_path, parent_path)


@mcp.tool()
async def tool_assign_bus(object_path: str, bus_path: str) -> dict:
    """
    将对象路由到指定 Bus（设置 OutputBus）。

    Args:
        object_path: 目标 Sound/Container 的路径
        bus_path:    目标 Bus 的完整路径，如 '\\\\Master-Mixer Hierarchy\\\\Master Audio Bus\\\\SFX'
    """
    await _ensure_connection()
    return await assign_bus(object_path, bus_path)



@mcp.tool()
async def tool_delete_object(object_path: str, force: bool = False) -> dict:
    """
    删除 Wwise 对象。

    Args:
        object_path: 要删除对象的完整路径
        force:       False（默认）先检查引用再删除；True 跳过引用检查直接删除

    注意：删除前建议先调用 verify_structure 确认无悬空引用。
    """
    await _ensure_connection()
    return await delete_object(object_path, force)


@mcp.tool()
async def tool_move_object(object_path: str, new_parent_path: str) -> dict:
    """
    将对象移动到新父节点（整理项目结构时使用）。

    Args:
        object_path:     要移动对象的完整路径
        new_parent_path: 目标父节点路径
    """
    await _ensure_connection()
    return await move_object(object_path, new_parent_path)


# --- 验证类（2 个）---

@mcp.tool()
async def tool_verify_structure(scope_path: str | None = None) -> dict:
    """
    结构完整性验证。每完成一个独立操作目标后调用此工具。

    检查项：Event→Action 关联、Action→Target 引用、Bus 路由、属性值范围、孤立对象。

    Args:
        scope_path: 验证范围路径（None 表示全项目验证）
    """
    await _ensure_connection()
    return await verify_structure(scope_path)


@mcp.tool()
async def tool_verify_event_completeness(event_path: str) -> dict:
    """
    专项验证：检查 Event 在 Wwise 2024.1 Auto-Defined SoundBank 场景下是否可正常触发。

    检查：Event存在 → Action完整 → Target引用有效 → AudioFileSource有音频文件 → Auto-Defined Bank已就绪。

    Args:
        event_path: 要验证的 Event 完整路径
    """
    await _ensure_connection()
    return await verify_event_completeness(event_path)


# --- 兜底类（1 个）---

@mcp.tool()
async def tool_execute_waapi(
    uri: str,
    args: dict = {},
    opts: dict = {},
) -> dict:
    """
    直接执行原始 WAAPI 调用（兜底工具，当预定义工具无法满足需求时使用）。

    Args:
        uri:  WAAPI 函数 URI，如 'ak.wwise.core.object.get'
        args: WAAPI arguments 参数字典
        opts: WAAPI options 参数字典

    安全限制：以下操作被黑名单禁止：
    project.open / project.close / project.save / remote.connect / remote.disconnect
    """
    await _ensure_connection()
    return await execute_waapi(uri, args, opts)


# ------------------------------------------------------------------
# System Prompt（作为 MCP Resource 暴露）
# ------------------------------------------------------------------

@mcp.resource("wwise://system_prompt")
async def get_system_prompt() -> str:
    """Wwise 2024.1 领域 System Prompt（供 MCP Client 获取并注入到 LLM）"""
    await _ensure_connection()
    dynamic = await build_dynamic_context()
    return STATIC_SYSTEM_PROMPT + dynamic


# ------------------------------------------------------------------
# 入口
# ------------------------------------------------------------------

def main():
    """命令行启动入口"""
    import argparse
    parser = argparse.ArgumentParser(description="WwiseMCP Server — Wwise 2024.1 AI Agent")
    parser.add_argument("--host", default=settings.host, help="Wwise WAAPI host（默认 127.0.0.1）")
    parser.add_argument("--port", type=int, default=settings.port, help="Wwise WAAPI port（默认 8080）")
    parser.add_argument("--transport", choices=["stdio", "sse"], default="stdio",
                        help="MCP 传输模式：stdio（Cursor/Claude Desktop）或 sse")
    parser.add_argument("--sse-port", type=int, default=8765, help="SSE 模式监听端口（默认 8765）")
    args = parser.parse_args()

    # 覆盖配置
    settings.host = args.host
    settings.port = args.port

    logger.info("WwiseMCP Server 启动，WAAPI 目标：%s，传输模式：%s", settings.waapi_url, args.transport)

    if args.transport == "sse":
        mcp.run(transport="sse", host="127.0.0.1", port=args.sse_port)
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
