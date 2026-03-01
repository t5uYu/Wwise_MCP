"""
WAAPI + WwiseBridge connection check script

Run this while Wwise is open to verify connections before starting wwise-mcp.

Usage:
    python check_waapi.py
    python check_waapi.py --port 9090
    python check_waapi.py --bridge-port 8082
"""

import asyncio
import argparse


def check_waapi(host: str, port: int) -> str | None:
    """Synchronous WAAPI check (waapi-client manages its own event loop)."""
    url = f"ws://{host}:{port}/waapi"
    print(f"Connecting to {url} ...")

    try:
        from waapi import WaapiClient
        with WaapiClient(url=url) as client:
            result = client.call("ak.wwise.core.getInfo") or {}
            version = result.get("version", {}) or {}
            version_str = version.get("displayName", str(version))
            print(f"\n[OK] WAAPI: {version_str}")
            return version_str
    except Exception as e:
        print(f"\n[FAIL] WAAPI: {e}\n")
        print("To enable WAAPI in Wwise:")
        print("  1. Open Wwise with your project")
        print("  2. Menu: Project -> User Preferences")
        print(f"  3. Enable 'Wwise Authoring API (WAAPI)'")
        print(f"  4. Confirm port is {port} (default 8080)")
        print("  5. Click OK and re-run this script\n")
        return None


async def check_bridge_async(bridge_port: int) -> bool:
    """Async WwiseBridge check."""
    try:
        import websockets
    except ImportError:
        print("[SKIP] websockets not installed: pip install 'websockets>=12.0'")
        return False

    import json
    import uuid

    url = f"ws://127.0.0.1:{bridge_port}/bridge"
    request = {"id": str(uuid.uuid4()), "action": "ping"}

    try:
        async with websockets.connect(url, open_timeout=3, close_timeout=3) as ws:
            await ws.send(json.dumps(request))
            raw = await asyncio.wait_for(ws.recv(), timeout=3)
            resp = json.loads(raw)

        if resp.get("success"):
            data = resp.get("data", {})
            print(f"[OK] WwiseBridge port {bridge_port} - "
                  f"wwise_version: {data.get('wwise_version', '?')}")
            return True
        else:
            print(f"[FAIL] WwiseBridge returned error: {resp}")
            return False

    except Exception as e:
        print(f"[--] WwiseBridge not running (optional, won't affect basic tools)")
        print(f"     Start it with: python bridge_launcher.py")
        return False


def main():
    parser = argparse.ArgumentParser(description="Check Wwise WAAPI + WwiseBridge")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--bridge-port", type=int, default=8081)
    args = parser.parse_args()

    # WAAPI uses its own event loop — call it synchronously first
    waapi_version = check_waapi(args.host, args.port)

    # Bridge check uses asyncio websockets
    print(f"\n-- WwiseBridge (optional) --")
    asyncio.run(check_bridge_async(args.bridge_port))

    print()
    if waapi_version:
        print("[READY] All components connected. You can start wwise-mcp.\n")
    else:
        print("[WAIT] WAAPI not ready. Check Wwise settings and retry.\n")


if __name__ == "__main__":
    main()
