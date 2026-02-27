"""
Layer 6 — 动态上下文注入（区块 5）
根据用户消息按需收集 Wwise 项目状态，注入到 System Prompt
"""

import logging

from ..rag.context_collector import WwiseRAG

logger = logging.getLogger("wwise_mcp.prompts.dynamic")

_rag = WwiseRAG()


async def build_dynamic_context(user_message: str) -> str:
    """
    根据用户消息收集相关 Wwise 项目状态，格式化为可注入的字符串。

    Args:
        user_message: 用户原始消息文本

    Returns:
        格式化的动态上下文字符串（约 200-600 tokens）
    """
    contexts = await _rag.collect(user_message)
    if not contexts:
        return ""

    # 按优先级排序输出
    order = [
        "project_info",
        "selected_objects",
        "actor_mixer_hierarchy",
        "bus_topology",
        "event_overview",
        "rtpc_list",
        "soundbank_info",
    ]

    lines = []
    for key in order:
        if key in contexts:
            lines.append(contexts[key])

    # 收集顺序中未出现的其他 key
    for key, value in contexts.items():
        if key not in order:
            lines.append(value)

    return "\n\n".join(lines)
