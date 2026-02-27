"""
Layer 4 — 查询类工具（7 个）
"""

import logging
from typing import Any, Optional

from ..core.adapter import WwiseAdapter
from ..core.exceptions import WwiseMCPError

logger = logging.getLogger("wwise_mcp.tools.query")

# ---------- 统一结果包装 ----------

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


# ---------- 工具实现 ----------

async def get_project_hierarchy() -> dict:
    """
    获取 Wwise 项目顶层结构概览。

    返回各主要层级（Actor-Mixer、Master-Mixer、Events、SoundBanks 等）的对象数量。
    2024.1 注意：Auto-Defined SoundBank 场景下 SoundBanks 节点可能为空，属正常行为。
    """
    try:
        adapter = WwiseAdapter()
        # 查询项目根节点下一层所有容器
        root_children = await adapter.get_objects(
            from_spec={"path": "\\"},
            return_fields=["@name", "@type", "@childrenCount", "@path"],
        )

        summary: dict[str, Any] = {}
        for obj in root_children:
            name = obj.get("@name", "")
            count = obj.get("@childrenCount", 0)
            obj_type = obj.get("@type", "")
            summary[name] = {"type": obj_type, "childrenCount": count, "path": obj.get("@path", "")}

        # 补充 Wwise 版本信息
        info = await adapter.get_info()
        return _ok({
            "wwise_version": info.get("version", {}).get("displayName", "Unknown"),
            "project_name": info.get("projectName", "Unknown"),
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
        page:        分页页码（从 1 开始），属性超过 page_size 时自动分页
        page_size:   每页返回属性数量，默认 30

    Returns:
        对象基础信息 + 属性字典，超出 page_size 时附带分页信息
    """
    try:
        adapter = WwiseAdapter()
        # 查询基础信息
        basic_fields = ["@name", "@type", "@path", "@id", "@shortId", "@notes"]
        key_props = [
            "Volume", "Pitch", "LowPassFilter", "HighPassFilter",
            "OutputBus", "OutputBusVolume", "OutputBusMixerGain",
            "Positioning.EnablePositioning", "Positioning.SpeakerPanning",
            "MakeUpGain", "InnerRadius", "OuterRadius",
            "MaxSoundInstances", "UseGameDefinedAuxSends",
        ]
        return_fields = basic_fields + key_props

        objects = await adapter.get_objects(
            from_spec={"path": object_path},
            return_fields=return_fields,
        )

        if not objects:
            return _err_raw(
                "not_found",
                f"对象不存在：{object_path}",
                f"请先调用 search_objects 搜索正确路径",
            )

        obj = objects[0]

        # 获取完整属性和引用名称列表
        try:
            prop_result = await adapter.call(
                "ak.wwise.core.object.getPropertyAndReferenceNames",
                {"object": {"path": object_path}},
            )
            all_props = prop_result.get("return", [])
        except Exception:
            all_props = []

        # 分页
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
        type_filter: 可选类型过滤，如 'Sound SFX', 'Event', 'Bus', 'GameParameter' 等
        max_results: 最多返回结果数，默认 20

    Returns:
        匹配对象列表，按路径排序
    """
    try:
        adapter = WwiseAdapter()

        where_clause: list = [["@name", "contains", query]]
        if type_filter:
            where_clause.append(["@type", "=", type_filter])

        args: dict[str, Any] = {
            "from": {"ofType": ["Sound SFX", "Sound Voice", "Event", "Bus",
                                "GameParameter", "Effect", "State", "Switch",
                                "MusicSegment", "MusicTrack", "BlendContainer",
                                "RandomSequenceContainer", "SwitchContainer"]
                     if not type_filter else [type_filter]},
            "where": [["@name", "contains", query]],
            "transform": [{"select": ["this"]}],
        }

        result = await adapter.call(
            "ak.wwise.core.object.get",
            args,
            {"return": ["@name", "@type", "@path", "@id"]},
        )
        objects = result.get("return", [])

        # 按路径排序，截断到 max_results
        objects.sort(key=lambda x: x.get("@path", ""))
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

    返回 Bus 树，包含每个 Bus 的名称、类型、父子关系。
    用于理解当前项目的混音路由架构。
    """
    try:
        adapter = WwiseAdapter()
        args = {
            "from": {"path": "\\Master-Mixer Hierarchy"},
            "transform": [
                {"select": ["descendants"]},
                {"where": [["@type", "=", "Bus"]]},
            ],
        }
        result = await adapter.call(
            "ak.wwise.core.object.get",
            args,
            {"return": ["@name", "@type", "@path", "@id", "@childrenCount"]},
        )
        buses = result.get("return", [])

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

    Returns:
        Event 基础信息 + Action 列表（含每个 Action 的类型和 Target 引用）
    """
    try:
        adapter = WwiseAdapter()

        # 获取 Event 自身信息
        events = await adapter.get_objects(
            from_spec={"path": event_path},
            return_fields=["@name", "@type", "@path", "@id"],
        )
        if not events:
            return _err_raw("not_found", f"Event 不存在：{event_path}",
                            "请先调用 search_objects 搜索 Event 的正确路径")

        # 获取 Event 下的 Action 子节点
        args = {
            "from": {"path": event_path},
            "transform": [{"select": ["children"]}],
        }
        result = await adapter.call(
            "ak.wwise.core.object.get",
            args,
            {"return": ["@name", "@type", "@path", "@id", "ActionType", "Target"]},
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

    2024.1 注意：Auto-Defined SoundBank 默认开启，User-Defined SoundBank 需手动创建。
    """
    try:
        adapter = WwiseAdapter()

        if soundbank_name:
            args = {
                "from": {"path": f"\\SoundBanks\\{soundbank_name}"},
            }
        else:
            args = {
                "from": {"path": "\\SoundBanks"},
                "transform": [{"select": ["children"]}],
            }

        result = await adapter.call(
            "ak.wwise.core.object.get",
            args,
            {"return": ["@name", "@type", "@path", "@id"]},
        )
        banks = result.get("return", [])

        # 获取 Auto-Defined SoundBank 配置状态
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

    Returns:
        RTPC（Game Parameter）列表，含名称、路径、默认值范围
    """
    try:
        adapter = WwiseAdapter()
        args = {
            "from": {"ofType": ["GameParameter"]},
        }
        result = await adapter.call(
            "ak.wwise.core.object.get",
            args,
            {"return": ["@name", "@type", "@path", "@id", "Min", "Max", "InitialValue"]},
        )
        rtpcs = result.get("return", [])
        rtpcs.sort(key=lambda x: x.get("@path", ""))
        rtpcs = rtpcs[:max_results]

        return _ok({
            "total": len(rtpcs),
            "rtpcs": rtpcs,
        })
    except WwiseMCPError as e:
        return _err(e)
    except Exception as e:
        return _err_raw("unexpected_error", str(e))
