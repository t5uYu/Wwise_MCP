"""
临时测试脚本：验证修复后的 WwiseAdapter 工作正常
"""
import asyncio
from wwise_mcp.core.adapter import WwiseAdapter, init_connection


async def main():
    conn = init_connection()
    await conn.ensure_connected()
    adapter = WwiseAdapter()

    # 1. 项目信息
    print("--- 1. 项目信息 ---")
    info = await adapter.get_info()
    print(f"  {info.get('version', {}).get('displayName')}  project={info.get('projectName')}")

    # 2. Game Parameters
    print("\n--- 2. Game Parameters ---")
    items = await adapter.get_objects(
        from_spec={"ofType": ["GameParameter"]},
        return_fields=["name", "path"],
    )
    print(f"  找到 {len(items)} 个")
    for item in items[:3]:
        print(f"    {item['name']} → {item['path']}")

    # 3. Events
    print("\n--- 3. Events ---")
    items = await adapter.get_objects(
        from_spec={"ofType": ["Event"]},
        return_fields=["name", "path", "childrenCount"],
    )
    print(f"  找到 {len(items)} 个")
    for item in items[:3]:
        print(f"    {item['name']} ({item.get('childrenCount',0)} actions)")

    # 4. Sounds
    print("\n--- 4. Sounds ---")
    items = await adapter.get_objects(
        from_spec={"ofType": ["Sound"]},
        return_fields=["name", "path"],
    )
    print(f"  找到 {len(items)} 个")
    for item in items[:3]:
        print(f"    {item['name']}")

    await conn.close()
    print("\n=== 全部通过 ===")


asyncio.run(main())
