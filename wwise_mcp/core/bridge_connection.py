"""
WwiseBridge WebSocket connection

Provides a thin async client to the WwiseBridge C++ Authoring Plugin that
runs inside Wwise on ws://127.0.0.1:8081/bridge.

Phase 1 contract
----------------
- ping() → verifies the bridge is alive and returns its pong response
- ensure_connected() → returns False silently if the bridge is not loaded
  (never raises, so existing WAAPI tools are not affected)
- call() → generic action dispatcher for Phase 2+ tools
"""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any

try:
    import websockets
    _WS_AVAILABLE = True
except ImportError:
    _WS_AVAILABLE = False


class BridgeConnection:
    URL = "ws://127.0.0.1:8081/bridge"
    TIMEOUT = 3.0  # seconds — fail fast when Bridge is not running

    def __init__(self) -> None:
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def ping(self) -> dict[str, Any]:
        """Send a ping and return the pong response dict.

        Raises:
            ConnectionRefusedError / OSError  if the Bridge is not reachable.
        """
        return await self.call("ping")

    async def ensure_connected(self) -> bool:
        """Return True if the Bridge is alive, False otherwise (never raises)."""
        if not _WS_AVAILABLE:
            return False
        try:
            await asyncio.wait_for(self.ping(), timeout=self.TIMEOUT)
            return True
        except Exception:
            return False

    async def call(self, action: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Send an action to the Bridge and return the response dict.

        Args:
            action: Action name, e.g. ``"ping"``.
            params: Optional extra parameters merged into the request payload.

        Returns:
            Parsed JSON response from the Bridge.

        Raises:
            RuntimeError  if ``websockets`` is not installed.
            Various ``websockets`` / ``asyncio`` exceptions on connection failure.
        """
        if not _WS_AVAILABLE:
            raise RuntimeError(
                "The 'websockets' package is required for BridgeConnection. "
                "Install it with:  pip install 'websockets>=12.0'"
            )

        request: dict[str, Any] = {"id": str(uuid.uuid4()), "action": action}
        if params:
            request.update(params)

        async with websockets.connect(  # type: ignore[attr-defined]
            self.URL,
            open_timeout=self.TIMEOUT,
            close_timeout=self.TIMEOUT,
        ) as ws:
            await ws.send(json.dumps(request))
            raw = await asyncio.wait_for(ws.recv(), timeout=self.TIMEOUT)
            return json.loads(raw)


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_bridge: BridgeConnection | None = None


def get_bridge() -> BridgeConnection:
    """Return the shared BridgeConnection singleton."""
    global _bridge
    if _bridge is None:
        _bridge = BridgeConnection()
    return _bridge
