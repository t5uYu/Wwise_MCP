"""
Layer 4 — 查询类工具（7 个）
"""

import logging
from typing import Any, Optional

from ..core.adapter import WwiseAdapter
from ..core.exceptions import WwiseMCPError

logger = logging.getLogger("wwise_mcp.tools.query")


def _ok(data: Any) -> dict:
    return {"success": True, "data": data, "error": None}

def _err(e: WwiseMCPError) -> dict:
    return e.to_dict()

def _err_raw(code: str, message: str, suggestion: str | None = None) -> dict:
    return {
        "success": False,
        "data": None,
        "error": {"code": code, "message": message, "suggestion": suggestion},
    }


async def get_project_hierarchy() -> dict:
    """
    获取 Wwise 项目顶层结构概览。
    返回各主要层级的对象数量和类型。
    2024.1 注意：Auto-Defined SoundBank 场景下 SoundBanks 节点可能为空，属正常行为。
    """
    try:
        adapter = WwiseAdapter()

        # 获取项目名（来自根路径对象）
        root_obj = await adapter.get_objects(
            from_spec={"path": ["\\"]},
            return_fields=["name", "path"],
        )
        project_name = root_obj[0].get("name", "Unknown") if root_obj else "Unknown"

        # WAAPI 2024.1 不支持从根路径用 transform 获取子节点，
        # 直接查询各已知顶层路径（一次调用，path 为数组）
        known_roots = [
            "\\Actor-Mixer Hierarchy",
            "\\Master-Mixer Hierarchy",
            "\\Events",
            "\\SoundBanks",
            "\\Game Parameters",
            "\\Switches",
            "\\States",
            "\\Interactive Music Hierarchy",
            "\\Effects",
            "\\Attenuations",
        ]
        root_children = await adapter.get_objects(
            from_spec={"path": known_roots},
            return_fields=["name", "type", "childrenCount", "path"],
        )

        summary: dict[str, Any] = {}
        for obj in root_children:
            name = obj.get("name", "")
            summary[name] = {
                "type": obj.get("type", ""),
                "childrenCount": obj.get("childrenCount", 0),
                "path": obj.get("path", ""),
            }

        info = await adapter.get_info()
        return _ok({
            "wwise_version": info.get("version", {}).get("displayName", "Unknown"),
            "project_name": project_name,
            "hierarchy": summary,
        })
    except WwiseMCPError as e:
        return _err(e)
    except Exception as e:
        return _err_raw("unexpected_error", str(e))


async def get_object_properties(object_path: str, page: int = 1, page_size: int = 30) -> dict:
    """
    获取指定对象的属性详情。

    Args:
        object_path: WAAPI 路径格式，如 '\\Actor-Mixer Hierarchy\\Default Work Unit\\MySFX'
        page:        分页页码（从 1 开始）
        page_size:   每页返回属性数量，默认 30
    """
    try:
        adapter = WwiseAdapter()
        # 只请求通用字段；音频属性字段（Volume/Pitch 等）仅对 Sound 类型有效，
        # 混入其他类型（Event/Bus 等）会导致 WAAPI "Unknown accessor" 错误。
        # 具体属性名通过下方 getPropertyAndReferenceNames 获取。
        basic_fields = ["name", "type", "path", "id", "shortId", "notes"]

        objects = await adapter.get_objects(
            from_spec={"path": [object_path]},
            return_fields=basic_fields,
        )

        if not objects:
            return _err_raw(
                "not_found",
                f"对象不存在：{object_path}",
                "请先调用 search_objects 搜索正确路径",
            )

        obj = objects[0]

        try:
            prop_result = await adapter.call(
                "ak.wwise.core.object.getPropertyAndReferenceNames",
                {"object": object_path},
            )
            all_props = prop_result.get("return", []) if prop_result else []
        except Exception:
            all_props = []

        total = len(all_props)
        start = (page - 1) * page_size
        end = start + page_size
        paged_props = all_props[start:end]

        return _ok({
            "object": obj,
            "all_properties": paged_props,
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total_properties": total,
                "has_more": end < total,
            },
        })
    except WwiseMCPError as e:
        return _err(e)
    except Exception as e:
        return _err_raw("unexpected_error", str(e))


async def search_objects(
    query: str,
    type_filter: str | None = None,
    max_results: int = 20,
) -> dict:
    """
    按关键词模糊搜索 Wwise 对象。

    Args:
        query:       搜索关键词（对象名称模糊匹配）
        type_filter: 可选类型过滤，如 'Sound', 'Event', 'Bus', 'GameParameter' 等
        max_results: 最多返回结果数，默认 20
    """
    try:
        adapter = WwiseAdapter()

        args: dict[str, Any] = {
            "from": {
                "ofType": [type_filter] if type_filter else [
                    "Sound", "Event", "Bus", "AuxBus",
                    "GameParameter", "ActorMixer", "BlendContainer",
                    "RandomSequenceContainer", "SwitchContainer",
                ]
            },
            # 注意：WAAPI 2024.1 不支持顶层 where 参数，改为客户端过滤
        }

        result = await adapter.call(
            "ak.wwise.core.object.get",
            args,
            {"return": ["name", "type", "path", "id"]},
        )
        all_objects = result.get("return", []) if result else []

        # 客户端按名称子串过滤（不区分大小写）
        query_lower = query.lower()
        objects = [o for o in all_objects if query_lower in o.get("name", "").lower()]
        objects.sort(key=lambda x: x.get("path", ""))
        objects = objects[:max_results]

        return _ok({
            "query": query,
            "type_filter": type_filter,
            "count": len(objects),
            "objects": objects,
        })
    except WwiseMCPError as e:
        return _err(e)
    except Exception as e:
        return _err_raw("unexpected_error", str(e))


async def get_bus_topology() -> dict:
    """
    获取 Master-Mixer Hierarchy 中所有 Bus 的拓扑结构。
    """
    try:
        adapter = WwiseAdapter()
        args = {
            "from": {"path": ["\\Master-Mixer Hierarchy"]},
            "transform": [{"select": ["descendants"]}],
            # 注意：transform where 在 WAAPI 2024.1 中不支持，改为客户端过滤
        }
        result = await adapter.call(
            "ak.wwise.core.object.get",
            args,
            {"return": ["name", "type", "path", "id", "childrenCount"]},
        )
        all_descendants = result.get("return", []) if result else []
        buses = [o for o in all_descendants if o.get("type") == "Bus"]

        return _ok({
            "total_buses": len(buses),
            "buses": buses,
        })
    except WwiseMCPError as e:
        return _err(e)
    except Exception as e:
        return _err_raw("unexpected_error", str(e))


async def get_event_actions(event_path: str) -> dict:
    """
    获取指定 Event 下所有 Action 的详情。

    Args:
        event_path: Event 对象的完整 WAAPI 路径
    """
    try:
        adapter = WwiseAdapter()

        events = await adapter.get_objects(
            from_spec={"path": [event_path]},
            return_fields=["name", "type", "path", "id"],
        )
        if not events:
            return _err_raw("not_found", f"Event 不存在：{event_path}",
                            "请先调用 search_objects 搜索 Event 的正确路径")

        args = {
            "from": {"path": [event_path]},
            "transform": [{"select": ["children"]}],
        }
        result = await adapter.call(
            "ak.wwise.core.object.get",
            args,
            {"return": ["name", "type", "path", "id", "ActionType", "Target"]},
        )
        actions = result.get("return", [])

        return _ok({
            "event": events[0],
            "action_count": len(actions),
            "actions": actions,
        })
    except WwiseMCPError as e:
        return _err(e)
    except Exception as e:
        return _err_raw("unexpected_error", str(e))


async def get_soundbank_info(soundbank_name: str | None = None) -> dict:
    """
    获取 SoundBank 信息。

    Args:
        soundbank_name: 指定 SoundBank 名称；为 None 时返回所有 SoundBank 概览。
    """
    try:
        adapter = WwiseAdapter()

        if soundbank_name:
            args = {"from": {"path": [f"\\SoundBanks\\{soundbank_name}"]}}
        else:
            args = {
                "from": {"path": ["\\SoundBanks"]},
                "transform": [{"select": ["children"]}],
            }

        result = await adapter.call(
            "ak.wwise.core.object.get",
            args,
            {"return": ["name", "type", "path", "id"]},
        )
        banks = result.get("return", [])

        try:
            project_info = await adapter.get_info()
            auto_soundbank = project_info.get("projectSettings", {}).get("autoSoundBank", True)
        except Exception:
            auto_soundbank = "unknown"

        return _ok({
            "auto_defined_soundbank_enabled": auto_soundbank,
            "soundbank_count": len(banks),
            "soundbanks": banks,
            "note": "Wwise 2024.1 默认开启 Auto-Defined SoundBank，无需手动管理 Bank 加载/卸载",
        })
    except WwiseMCPError as e:
        return _err(e)
    except Exception as e:
        return _err_raw("unexpected_error", str(e))


async def get_rtpc_list(max_results: int = 50) -> dict:
    """
    获取项目中所有 Game Parameter（RTPC）列表。

    Args:
        max_results: 最多返回数量，默认 50
    """
    try:
        adapter = WwiseAdapter()
        result = await adapter.call(
            "ak.wwise.core.object.get",
            {"from": {"ofType": ["GameParameter"]}},
            {"return": ["name", "type", "path", "id", "Min", "Max", "InitialValue"]},
        )
        rtpcs = result.get("return", [])
        rtpcs.sort(key=lambda x: x.get("path", ""))
        rtpcs = rtpcs[:max_results]

        return _ok({
            "total": len(rtpcs),
            "rtpcs": rtpcs,
        })
    except WwiseMCPError as e:
        return _err(e)
    except Exception as e:
        return _err_raw("unexpected_error", str(e))
