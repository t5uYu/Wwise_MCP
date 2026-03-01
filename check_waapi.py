"""
WAAPI 连接检查脚本

在 Wwise 打开的情况下运行此脚本，验证 WAAPI 连接是否正常。
确认连接正常后，再启动 wwise-mcp。

用法：
    python check_waapi.py
    python check_waapi.py --port 9090   # 自定义端口
"""

import asyncio
import argparse


async def check_connection(host: str, port: int) -> None:
    url = f"ws://{host}:{port}/waapi"
    print(f"正在连接 {url} ...")

    try:
        from waapi import WaapiClient
        async with WaapiClient(url=url) as client:
            result = await client.call("ak.wwise.core.getInfo")
            version = result.get("version", {})
            version_str = version.get("displayName", str(version))
            print(f"\n✓ 连接成功！Wwise 版本：{version_str}")
            print("→ 可以启动 wwise-mcp 了。\n")
            print("  Claude Desktop / Cursor 配置示例：")
            print('  "command": "wwise-mcp"')
            print(f'  或 "args": ["-m", "wwise_mcp.server"]')
    except Exception as e:
        print(f"\n✗ 连接失败：{e}\n")
        print("请按以下步骤在 Wwise 中启用 WAAPI：")
        print("  1. 打开 Wwise，加载你的项目")
        print(f"  2. 菜单：Edit → Preferences → User Preferences")
        print(f"  3. 找到「Enable Wwise Authoring API（WAAPI）」，勾选启用")
        print(f"  4. 确认端口号为 {port}（默认 8080）")
        print("  5. 点击 OK，重新运行此脚本\n")


def main():
    parser = argparse.ArgumentParser(description="检查 Wwise WAAPI 连接")
    parser.add_argument("--host", default="127.0.0.1", help="WAAPI host（默认 127.0.0.1）")
    parser.add_argument("--port", type=int, default=8080, help="WAAPI port（默认 8080）")
    args = parser.parse_args()
    asyncio.run(check_connection(args.host, args.port))


if __name__ == "__main__":
    main()
