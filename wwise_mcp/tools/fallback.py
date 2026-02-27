"""
Layer 4 — 兜底工具：execute_waapi
直接执行原始 WAAPI 调用，黑名单过滤危险操作。
"""

import logging
from typing import Any

from ..core.adapter import WwiseAdapter
from ..core.exceptions import WwiseMCPError, WwiseForbiddenOperationError
from ..config import settings

logger = logging.getLogger("wwise_mcp.tools.fallback")


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


async def execute_waapi(uri: str, args: dict = {}, opts: dict = {}) -> dict:
    """
    直接执行原始 WAAPI 调用（兜底工具）。

    用于预定义工具未覆盖的操作，或调试时需要精确控制 WAAPI 参数的场景。
    受黑名单保护，以下操作被禁止：project.open/close/save、remote.connect/disconnect 等。

    Args:
        uri:  WAAPI 函数 URI，如 'ak.wwise.core.object.get'
        args: WAAPI arguments 参数字典
        opts: WAAPI options 参数字典（控制返回字段等）

    Returns:
        WAAPI 原始返回结果

    安全限制（黑名单）：
      - ak.wwise.core.project.open
      - ak.wwise.core.project.close
      - ak.wwise.core.project.save
      - ak.wwise.ui.project.open
      - ak.wwise.core.remote.connect
      - ak.wwise.core.remote.disconnect
    """
    # 黑名单检查
    for blocked_uri in settings.blacklisted_uris:
        if uri.startswith(blocked_uri):
            forbidden_error = WwiseForbiddenOperationError(uri)
            logger.warning("拒绝黑名单操作：%s（来自 execute_waapi）", uri)
            return forbidden_error.to_dict()

    try:
        adapter = WwiseAdapter()
        result = await adapter.call(uri, args, opts)
        return _ok(result)
    except WwiseMCPError as e:
        return _err(e)
    except Exception as e:
        return _err_raw("unexpected_error", str(e))
