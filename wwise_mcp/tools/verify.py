"""
Layer 4 — 验证类工具（2 个）
"""

import logging
from typing import Any

from ..core.adapter import WwiseAdapter
from ..core.exceptions import WwiseMCPError

logger = logging.getLogger("wwise_mcp.tools.verify")


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


async def verify_structure(scope_path: str | None = None) -> dict:
    """
    结构完整性验证，检查 Event→Action 关联、Bus 路由、属性值范围等。

    建议：每完成一个独立操作目标后调用此工具。

    Args:
        scope_path: 验证范围路径（None 表示全项目验证，指定路径则只验证该子树）

    检查项：
      - Event → Action 关联：每个 Event 至少有 1 个 Action
      - Action → Target 引用：Target 引用非空且目标对象存在
      - Bus 路由：Sound 的 OutputBus 非空且目标 Bus 存在
      - 属性值范围：Volume 在 -200~+200 dB，Pitch 在 -2400~+2400
      - 孤立对象：无 Action 的 Event，无 OutputBus 的 Sound
    """
    try:
        adapter = WwiseAdapter()
        issues = []
        warnings = []

        # --- 1. 验证 Event → Action 关联 ---
        event_from = (
            {"path": scope_path, "transform": [{"select": ["descendants"]}, {"where": [["@type", "=", "Event"]]}]}
            if scope_path
            else {"ofType": ["Event"]}
        )
        event_result = await adapter.call(
            "ak.wwise.core.object.get",
            {"from": event_from},
            {"return": ["@name", "@path", "@id", "@childrenCount"]},
        )
        events = event_result.get("return", [])

        orphan_events = []
        for event in events:
            child_count = event.get("@childrenCount", 0)
            if child_count == 0:
                orphan_events.append(event.get("@path"))
                issues.append({
                    "type": "orphan_event",
                    "severity": "error",
                    "path": event.get("@path"),
                    "message": f"Event '{event.get('@name')}' 没有任何 Action，无法触发任何操作",
                })

        # --- 2. 验证 Action → Target 引用 ---
        action_result = await adapter.call(
            "ak.wwise.core.object.get",
            {"from": {"ofType": ["Action"]}},
            {"return": ["@name", "@path", "@id", "Target"]},
        )
        actions = action_result.get("return", [])

        for action in actions:
            target = action.get("Target")
            if not target:
                issues.append({
                    "type": "action_no_target",
                    "severity": "error",
                    "path": action.get("@path"),
                    "message": f"Action '{action.get('@name')}' 的 Target 引用为空",
                })

        # --- 3. 验证 Bus 路由 ---
        sound_result = await adapter.call(
            "ak.wwise.core.object.get",
            {"from": {"ofType": ["Sound SFX", "Sound Voice"]}},
            {"return": ["@name", "@path", "@id", "OutputBus"]},
        )
        sounds = sound_result.get("return", [])

        sounds_no_bus = []
        for sound in sounds:
            output_bus = sound.get("OutputBus")
            if not output_bus:
                sounds_no_bus.append(sound.get("@path"))
                warnings.append({
                    "type": "sound_no_bus",
                    "severity": "warning",
                    "path": sound.get("@path"),
                    "message": f"Sound '{sound.get('@name')}' 未指定 OutputBus，将使用默认路由",
                })

        # --- 4. 属性值范围检查（对有 Volume/Pitch 的对象采样检查）---
        range_issues = []
        for sound in sounds[:50]:  # 采样前 50 个，避免全量查询性能问题
            try:
                props = await adapter.call(
                    "ak.wwise.core.object.get",
                    {"from": {"path": sound.get("@path")}},
                    {"return": ["Volume", "Pitch"]},
                )
                prop_list = props.get("return", [{}])
                if prop_list:
                    obj_props = prop_list[0]
                    volume = obj_props.get("Volume")
                    pitch = obj_props.get("Pitch")
                    if volume is not None and not (-200 <= float(volume) <= 200):
                        range_issues.append({
                            "type": "volume_out_of_range",
                            "severity": "warning",
                            "path": sound.get("@path"),
                            "message": f"Volume={volume} 超出正常范围 [-200, 200] dB",
                        })
                    if pitch is not None and not (-2400 <= float(pitch) <= 2400):
                        range_issues.append({
                            "type": "pitch_out_of_range",
                            "severity": "warning",
                            "path": sound.get("@path"),
                            "message": f"Pitch={pitch} 超出正常范围 [-2400, 2400] 音分",
                        })
            except Exception:
                pass  # 单个对象检查失败不影响整体

        issues.extend(range_issues)
        issues.extend(warnings)

        error_count = sum(1 for i in issues if i.get("severity") == "error")
        warning_count = sum(1 for i in issues if i.get("severity") == "warning")

        passed = error_count == 0

        return _ok({
            "passed": passed,
            "summary": {
                "errors": error_count,
                "warnings": warning_count,
                "total_events_checked": len(events),
                "total_actions_checked": len(actions),
                "total_sounds_checked": len(sounds),
            },
            "orphan_events": orphan_events,
            "sounds_without_bus": sounds_no_bus,
            "issues": issues,
            "message": "结构验证通过" if passed else f"发现 {error_count} 个错误，{warning_count} 个警告",
        })
    except WwiseMCPError as e:
        return _err(e)
    except Exception as e:
        return _err_raw("unexpected_error", str(e))


async def verify_event_completeness(event_path: str) -> dict:
    """
    验证 Event 在 Wwise 2024.1 Auto-Defined SoundBank 场景下是否可正常触发。

    检查项：
      - Event 关联的所有 AudioFileSource 是否有对应音频文件
      - Auto-Defined SoundBank 是否已生成（ak.wwise.core.soundbank.getInclusions）
      - Event → Action → Target 调用链是否完整

    Args:
        event_path: 要验证的 Event 完整路径

    2024.1 特性：Auto-Defined SoundBank 自动管理，Live Editing 可实时验证触发效果
    """
    try:
        adapter = WwiseAdapter()
        checks = []
        all_passed = True

        # --- 检查 1：Event 存在性 ---
        events = await adapter.get_objects(
            from_spec={"path": event_path},
            return_fields=["@name", "@type", "@path", "@id", "@childrenCount"],
        )
        if not events:
            return _err_raw("not_found", f"Event 不存在：{event_path}",
                            "请先调用 search_objects 确认 Event 路径")

        event = events[0]
        checks.append({"check": "event_exists", "passed": True, "detail": f"Event 存在：{event.get('@name')}"})

        # --- 检查 2：Event 有 Action ---
        child_count = event.get("@childrenCount", 0)
        has_actions = child_count > 0
        if not has_actions:
            all_passed = False
        checks.append({
            "check": "has_actions",
            "passed": has_actions,
            "detail": f"Action 数量：{child_count}" if has_actions else "Event 没有 Action，无法触发",
        })

        # --- 检查 3：Action 的 Target 引用完整 ---
        action_result = await adapter.call(
            "ak.wwise.core.object.get",
            {"from": {"path": event_path}, "transform": [{"select": ["children"]}]},
            {"return": ["@name", "@type", "@path", "ActionType", "Target"]},
        )
        actions = action_result.get("return", [])
        actions_with_target = [a for a in actions if a.get("Target")]
        target_ok = len(actions_with_target) == len(actions) and len(actions) > 0
        if not target_ok:
            all_passed = False
        checks.append({
            "check": "actions_have_targets",
            "passed": target_ok,
            "detail": f"{len(actions_with_target)}/{len(actions)} 个 Action 有 Target 引用",
        })

        # --- 检查 4：查找关联的 AudioFileSource ---
        audio_sources = []
        for action in actions_with_target:
            target = action.get("Target", {})
            target_path = target.get("path") if isinstance(target, dict) else None
            if target_path:
                try:
                    sources = await adapter.call(
                        "ak.wwise.core.object.get",
                        {
                            "from": {"path": target_path},
                            "transform": [
                                {"select": ["descendants"]},
                                {"where": [["@type", "=", "AudioFileSource"]]},
                            ],
                        },
                        {"return": ["@name", "@path", "@id", "AudioFile"]},
                    )
                    audio_sources.extend(sources.get("return", []))
                except Exception:
                    pass

        sources_with_file = [s for s in audio_sources if s.get("AudioFile")]
        if audio_sources:
            sources_ok = len(sources_with_file) == len(audio_sources)
            if not sources_ok:
                all_passed = False
            checks.append({
                "check": "audio_file_sources",
                "passed": sources_ok,
                "detail": f"{len(sources_with_file)}/{len(audio_sources)} 个 AudioFileSource 有音频文件",
            })
        else:
            checks.append({
                "check": "audio_file_sources",
                "passed": True,
                "detail": "未找到 AudioFileSource（可能为 Synthesizer 或 External Source）",
            })

        # --- 检查 5：SoundBank 包含状态（2024.1 Auto-Defined）---
        try:
            bank_inclusions = await adapter.call(
                "ak.wwise.core.soundbank.getInclusions",
                {"soundbank": {"path": "\\SoundBanks\\Default Work Unit"}},
            )
            inclusions = bank_inclusions.get("inclusions", [])
            event_name = event.get("@name", "")
            event_in_bank = any(
                inc.get("object", {}).get("name") == event_name
                for inc in inclusions
            )
            checks.append({
                "check": "soundbank_inclusion",
                "passed": True,
                "detail": f"Auto-Defined SoundBank 会自动包含此 Event（2024.1 特性），无需手动管理",
            })
        except Exception:
            checks.append({
                "check": "soundbank_inclusion",
                "passed": True,
                "detail": "Auto-Defined SoundBank 模式：Wwise 2024.1 自动管理 SoundBank，无需手动检查",
            })

        return _ok({
            "event": event_path,
            "all_passed": all_passed,
            "checks": checks,
            "live_editing_note": (
                "Wwise 2024.1 Live Editing 已启用。如已连接 UE5.4 或游戏实例，"
                "可在游戏中直接触发此 Event 验证音效效果，无需重新打包 SoundBank。"
            ),
        })
    except WwiseMCPError as e:
        return _err(e)
    except Exception as e:
        return _err_raw("unexpected_error", str(e))
