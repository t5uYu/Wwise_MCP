"""
Layer 4 — 操作类工具（8 个）
"""

import logging
from typing import Any, Union

from ..core.adapter import WwiseAdapter
from ..core.exceptions import WwiseMCPError
from ..rag.doc_index import doc_index

logger = logging.getLogger("wwise_mcp.tools.action")


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


async def create_object(
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
        obj_type:    对象类型，如 'Sound SFX', 'Event', 'Bus', 'BlendContainer' 等
        parent_path: 父对象的完整 WAAPI 路径
        on_conflict: 名称冲突处理策略：'rename'（默认）| 'replace' | 'fail'
        notes:       备注（可选）

    Returns:
        新对象的 {id, name, path}
    """
    try:
        adapter = WwiseAdapter()

        # 安全检查：先确认同名对象是否已存在
        existing = await adapter.get_objects(
            from_spec={"path": parent_path},
            return_fields=["name", "path"],
        )
        existing_names = {obj.get("name") for obj in existing}
        if name in existing_names and on_conflict == "fail":
            return _err_raw(
                "conflict",
                f"父节点 '{parent_path}' 下已存在同名对象 '{name}'",
                "可将 on_conflict 设为 'rename' 自动重命名，或先删除已有对象",
            )

        result = await adapter.create_object(
            name=name,
            obj_type=obj_type,
            parent_path=parent_path,
            on_conflict=on_conflict,
            notes=notes,
        )
        return _ok({
            "id": result.get("id"),
            "name": result.get("name"),
            "path": result.get("path"),
            "type": obj_type,
        })
    except WwiseMCPError as e:
        return _err(e)
    except Exception as e:
        return _err_raw("unexpected_error", str(e))


async def set_property(
    object_path: str,
    property: str | None = None,
    value: Union[float, str, bool, None] = None,
    properties: dict | None = None,
    platform: str | None = None,
) -> dict:
    """
    设置对象的一个或多个属性。

    Args:
        object_path: 目标对象路径
        property:    单个属性名，如 'Volume', 'Pitch', 'LowPassFilter'
        value:       单个属性值
        properties:  批量属性字典，如 {"Volume": -6.0, "Pitch": 200}
        platform:    目标平台（None 表示所有平台）

    注意：property+value 与 properties 二选一，优先使用 properties（批量更高效）
    """
    try:
        adapter = WwiseAdapter()

        # 统一为批量模式
        if properties is None:
            if property is None or value is None:
                return _err_raw(
                    "invalid_param",
                    "必须提供 property+value 或 properties 参数",
                )
            properties = {property: value}

        results = []
        for prop_name, prop_value in properties.items():
            # 防御性校验：属性名必须在已知白名单中
            if not doc_index.is_valid_property(prop_name):
                suggestions = doc_index.get_similar_properties(prop_name)
                results.append({
                    "property": prop_name,
                    "value": prop_value,
                    "success": False,
                    "error": f"未知属性名 '{prop_name}'，请检查拼写",
                    "suggestion": f"相近的合法属性名：{suggestions}" if suggestions else "请调用 get_object_properties 获取合法属性列表",
                })
                continue
            try:
                await adapter.set_property(object_path, prop_name, prop_value, platform)
                results.append({"property": prop_name, "value": prop_value, "success": True})
            except Exception as e:
                results.append({"property": prop_name, "value": prop_value, "success": False, "error": str(e)})

        all_success = all(r["success"] for r in results)
        return _ok({
            "object_path": object_path,
            "results": results,
            "all_success": all_success,
        })
    except WwiseMCPError as e:
        return _err(e)
    except Exception as e:
        return _err_raw("unexpected_error", str(e))


async def create_event(
    event_name: str,
    action_type: str,
    target_path: str,
    parent_path: str = "\\Events\\Default Work Unit",
) -> dict:
    """
    创建 Wwise Event 及其 Action。

    操作顺序（必须严格遵守）：
      1. 创建 Event 对象
      2. 在 Event 下创建 Action
      3. 设置 Action 的 Target 引用

    Args:
        event_name:  Event 名称，建议以动词开头，如 'Play_Explosion'
        action_type: Action 类型：'Play' | 'Stop' | 'Pause' | 'Resume' | 'Break' | 'Mute' | 'UnMute'
        target_path: Action 目标对象路径（Sound/Container 等）
        parent_path: Event 的父节点路径，默认 Default Work Unit

    2024.1 优化：利用 Live Editing 特性，创建后无需生成 SoundBank 即可验证
    """
    try:
        adapter = WwiseAdapter()

        # Step 1: 创建 Event 对象
        event_result = await adapter.create_object(
            name=event_name,
            obj_type="Event",
            parent_path=parent_path,
            on_conflict="rename",
        )
        event_path = event_result.get("path")
        if not event_path:
            return _err_raw("waapi_error", f"创建 Event '{event_name}' 失败：未返回对象路径")

        # Step 2: 在 Event 下创建 Action
        action_name = f"{action_type}_{event_name}"
        action_result = await adapter.create_object(
            name=action_name,
            obj_type="Action",
            parent_path=event_path,
            on_conflict="rename",
        )
        action_path = action_result.get("path")
        if not action_path:
            return _err_raw("waapi_error", f"在 Event 下创建 Action 失败")

        # Step 3: 设置 Action 类型
        action_type_map = {
            "Play": 1, "Stop": 2, "Pause": 3, "Resume": 4,
            "Break": 28, "Mute": 6, "UnMute": 7,
        }
        action_type_id = action_type_map.get(action_type, 1)
        await adapter.set_property(action_path, "ActionType", action_type_id)

        # Step 4: 设置 Action 的 Target 引用
        await adapter.set_reference(action_path, "Target", target_path)

        return _ok({
            "event": {
                "id": event_result.get("id"),
                "name": event_name,
                "path": event_path,
            },
            "action": {
                "id": action_result.get("id"),
                "name": action_name,
                "path": action_path,
                "type": action_type,
                "target": target_path,
            },
            "note": "Wwise 2024.1 Live Editing 已启用，无需重新生成 SoundBank 即可立即验证",
        })
    except WwiseMCPError as e:
        return _err(e)
    except Exception as e:
        return _err_raw("unexpected_error", str(e))


async def assign_bus(object_path: str, bus_path: str) -> dict:
    """
    将对象路由到指定 Bus（设置 OutputBus）。

    Args:
        object_path: 目标 Sound/Container 的路径
        bus_path:    目标 Bus 的完整路径，如 '\\Master-Mixer Hierarchy\\Master Audio Bus\\SFX'
    """
    try:
        adapter = WwiseAdapter()
        await adapter.set_reference(object_path, "OutputBus", bus_path)
        return _ok({
            "object_path": object_path,
            "output_bus": bus_path,
        })
    except WwiseMCPError as e:
        return _err(e)
    except Exception as e:
        return _err_raw("unexpected_error", str(e))


async def set_rtpc_binding(
    object_path: str,
    property: str,
    game_parameter_path: str,
    curve_type: str = "Linear",
) -> dict:
    """
    将 Game Parameter（RTPC）绑定到对象属性。

    ⚠️ WAAPI 限制：Wwise WAAPI 2024.1 不支持通过 API 创建 RTPC 绑定。
    该操作需要在 Wwise 图形界面中手动完成。

    Args:
        object_path:          目标对象路径
        property:             要绑定的属性，如 'Volume', 'Pitch', 'LowPassFilter'
        game_parameter_path:  Game Parameter 路径，如 '\\Game Parameters\\Default Work Unit\\Distance'
        curve_type:           曲线类型：'Linear' | 'Log1' | 'Log2' | 'Exp1' | 'SCurve' | 'InvertedSCurve'
    """
    param_name = game_parameter_path.split("\\")[-1]
    return _err_raw(
        "waapi_not_supported",
        f"Wwise WAAPI 2024.1 不支持通过 API 创建 RTPC 绑定（将 Game Parameter 关联到对象属性）。"
        f"经实测确认：'Rtpc' 类型无法通过 ak.wwise.core.object.create 创建，"
        f"ak.wwise.core.object.addObjectToList 在 2024.1 中不存在。",
        f"请在 Wwise 中手动操作：选中对象 '{object_path.split(chr(92))[-1]}' "
        f"→ 属性编辑器 → 找到属性 '{property}' → 右键 → Add RTPC "
        f"→ 选择 Game Parameter '{param_name}'（曲线类型：{curve_type}）。",
    )


async def add_effect(
    object_path: str,
    effect_type: str,
    slot: int = 0,
    effect_name: str | None = None,
) -> dict:
    """
    在对象的效果器链上添加 Effect。

    ⚠️ WAAPI 限制：Wwise WAAPI 2024.1 不支持通过 API 在 Sound/Bus 上创建 Effect Slot。
    该操作需要在 Wwise 图形界面中手动完成。

    Args:
        object_path: 目标 Sound/Bus 路径
        effect_type: 效果器类型，如 'Wwise Compressor', 'Wwise Parametric EQ', 'Wwise RoomVerb'
        slot:        效果器插槽索引（0-3）
        effect_name: 效果器名称（可选）
    """
    obj_name = object_path.split("\\")[-1]
    return _err_raw(
        "waapi_not_supported",
        f"Wwise WAAPI 2024.1 不支持通过 API 在 Sound/Bus 对象上创建 Effect Slot。"
        f"经实测确认：EffectSlot 类型无法通过 ak.wwise.core.object.create 创建（Sound/Bus 均不允许），"
        f"Effect 类型对象也无法在 Effects 工作单元下通过 API 创建。",
        f"请在 Wwise 中手动操作：选中对象 '{obj_name}' "
        f"→ 属性编辑器 → Effects 标签页 → Effect Slot {slot} "
        f"→ 点击添加 → 选择效果器类型 '{effect_type}'。",
    )


async def delete_object(object_path: str, force: bool = False) -> dict:
    """
    删除 Wwise 对象。

    Args:
        object_path: 要删除对象的完整路径
        force:       True 时跳过引用检查，直接删除；False（默认）时先检查是否有其他对象引用该目标

    注意：删除前建议先调用 verify_structure 确认无悬空引用
    """
    try:
        adapter = WwiseAdapter()

        if not force:
            # 检查是否有 Action 引用此对象
            search_result = await adapter.call(
                "ak.wwise.core.object.get",
                {
                    "from": {"ofType": ["Action"]},
                    "where": [["Target:name", "=", object_path.split("\\")[-1]]],
                },
                {"return": ["name", "path", "Target"]},
            )
            referencing_actions = search_result.get("return", [])
            if referencing_actions:
                return _err_raw(
                    "has_references",
                    f"对象 '{object_path}' 被 {len(referencing_actions)} 个 Action 引用，删除可能导致悬空引用",
                    f"引用该对象的 Action：{[a.get('path') for a in referencing_actions[:5]]}。"
                    f"确认要强制删除请传入 force=True",
                )

        await adapter.delete_object(object_path)
        return _ok({"deleted": object_path})
    except WwiseMCPError as e:
        return _err(e)
    except Exception as e:
        return _err_raw("unexpected_error", str(e))


async def move_object(object_path: str, new_parent_path: str) -> dict:
    """
    将对象移动到新父节点。

    Args:
        object_path:     要移动对象的完整路径
        new_parent_path: 目标父节点路径

    Returns:
        移动后的新路径
    """
    try:
        adapter = WwiseAdapter()
        await adapter.move_object(object_path, new_parent_path)

        # 获取移动后的新路径
        obj_name = object_path.split("\\")[-1]
        new_path = f"{new_parent_path}\\{obj_name}"

        return _ok({
            "original_path": object_path,
            "new_path": new_path,
            "new_parent": new_parent_path,
        })
    except WwiseMCPError as e:
        return _err(e)
    except Exception as e:
        return _err_raw("unexpected_error", str(e))
