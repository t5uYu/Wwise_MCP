"""
WwiseBridge Launcher

Loads WwiseBridge.dll into this process so its built-in WebSocket server
starts listening on ws://127.0.0.1:8081/bridge.

Usage:
    python bridge_launcher.py
    python bridge_launcher.py --dll "D:\\path\\to\\WwiseBridge.dll"

Keep this running alongside Wwise. Ctrl+C to stop.
"""

import ctypes
import time
import argparse
import sys
import socket


DEFAULT_DLL = (
    r"D:\Audiokinetic\Wwise2024.1.8.8898"
    r"\Authoring\x64\Release\bin\Plugins\WwiseBridge.dll"
)
BRIDGE_PORT = 8081


def port_open(port: int) -> bool:
    s = socket.socket()
    result = s.connect_ex(("127.0.0.1", port))
    s.close()
    return result == 0


def main():
    parser = argparse.ArgumentParser(description="WwiseBridge DLL Launcher")
    parser.add_argument("--dll", default=DEFAULT_DLL, help="Path to WwiseBridge.dll")
    args = parser.parse_args()

    print(f"Loading {args.dll} ...")
    try:
        _dll = ctypes.WinDLL(args.dll)
    except OSError as e:
        print(f"ERROR: Failed to load DLL: {e}")
        sys.exit(1)

    # Give the static initialiser's background thread a moment to bind
    time.sleep(0.5)

    if port_open(BRIDGE_PORT):
        print(f"WwiseBridge running on ws://127.0.0.1:{BRIDGE_PORT}/bridge")
        print("Press Ctrl+C to stop.\n")
    else:
        print(f"WARNING: DLL loaded but port {BRIDGE_PORT} is not open.")
        print("         Check Windows Firewall or if another process holds the port.")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping WwiseBridge.")


if __name__ == "__main__":
    main()
