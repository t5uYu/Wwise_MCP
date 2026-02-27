"""
测试 v2：确认 object 参数格式 + RTPC/Effect 正确 API
"""
import json
from waapi import WaapiClient

def pp(label, obj):
    print(f"\n[{label}]")
    print(json.dumps(obj, indent=2, ensure_ascii=False, default=str))

with WaapiClient() as client:

    # 获取基础对象
    sounds = client.call("ak.wwise.core.object.get", {
        "from": {"ofType": ["Sound"]},
        "options": {"return": ["name", "path", "id"]}
    })
    sound = sounds["return"][0]
    sound_path = sound["path"]
    sound_id = sound["id"]

    params = client.call("ak.wwise.core.object.get", {
        "from": {"ofType": ["GameParameter"]},
        "options": {"return": ["name", "path", "id"]}
    })
    param = params["return"][0]
    param_path = param["path"]

    print(f"Sound: {sound_path}")
    print(f"Sound ID: {sound_id}")
    print(f"Param: {param_path}")

    # -----------------------------------------------
    # 1. 测试 set_property 的 object 参数格式
    # -----------------------------------------------
    print("\n=== 1. setProperty - object 格式测试 ===")

    # 1a. {"path": "..."} 格式
    r = client.call("ak.wwise.core.object.setProperty", {
        "object": {"path": sound_path},
        "property": "Volume",
        "value": -6.0
    })
    print(f"  1a. object={{'path': ...}} -> {r}")

    # 1b. 字符串格式
    r = client.call("ak.wwise.core.object.setProperty", {
        "object": sound_path,
        "property": "Volume",
        "value": -6.0
    })
    print(f"  1b. object=string -> {r}")

    # 1c. GUID 格式
    r = client.call("ak.wwise.core.object.setProperty", {
        "object": sound_id,
        "property": "Volume",
        "value": -6.0
    })
    print(f"  1c. object=guid -> {r}")

    # -----------------------------------------------
    # 2. getPropertyAndReferenceNames - 格式测试
    # -----------------------------------------------
    print("\n=== 2. getPropertyAndReferenceNames 格式测试 ===")

    # 2a. 字符串格式
    r = client.call("ak.wwise.core.object.getPropertyAndReferenceNames", {
        "object": sound_path
    })
    print(f"  2a. string -> {r}")

    # 2b. GUID 格式
    r = client.call("ak.wwise.core.object.getPropertyAndReferenceNames", {
        "object": sound_id
    })
    if r:
        print(f"  2b. guid -> properties: {r.get('properties', [])[:5]}...")
        print(f"          references: {r.get('references', [])[:5]}...")
    else:
        print(f"  2b. guid -> {r}")

    # -----------------------------------------------
    # 3. 查询有 RTPC 绑定的 Sound 的完整 RTPC 信息
    # -----------------------------------------------
    print("\n=== 3. 查询 Sound 的 RTPC 信息（通过 return 字段）===")

    # 尝试直接从 get_objects 返回 RTPC 信息
    r = client.call("ak.wwise.core.object.get", {
        "from": {"ofType": ["Sound"]},
        "options": {"return": ["name", "path", "RTPC", "rtpc"]}
    })
    print(f"  返回 RTPC 字段: {r}")

    # -----------------------------------------------
    # 4. 查询 Sound 的子对象（看 RTPC 是否作为子对象存在）
    # -----------------------------------------------
    print("\n=== 4. 查询特定 Sound 的所有子对象 ===")
    # 找一个已知有 RTPC 的 Sound（Enemies_EvilHead）
    eh_sounds = client.call("ak.wwise.core.object.get", {
        "from": {"path": ["\\Actor-Mixer Hierarchy\\Enemies\\EvilHead"]},
        "transform": [{"select": ["descendants"]}],
        "options": {"return": ["name", "type", "path", "id"]}
    })
    if eh_sounds and eh_sounds.get("return"):
        for obj in eh_sounds["return"]:
            if obj.get("type") == "Sound":
                sound_with_rtpc = obj
                print(f"  找到 EvilHead Sound: {obj['path']}")
                # 查询该Sound的子对象
                children = client.call("ak.wwise.core.object.get", {
                    "from": {"path": [obj["path"]]},
                    "transform": [{"select": ["children"]}],
                    "options": {"return": ["name", "type", "path", "id"]}
                })
                if children and children.get("return"):
                    child_types = [c.get('type','?') + ':' + c.get('name','?') for c in children['return']]
                    print(f"  子对象: {child_types}")
                    # 找 Rtpc 类型的子对象
                    rtpc_objs = [c for c in children["return"] if "rtpc" in c.get("type","").lower() or "rtpc" in c.get("name","").lower()]
                    if rtpc_objs:
                        print(f"  RTPC 子对象: {rtpc_objs}")
                        for ro in rtpc_objs:
                            # 查询 RTPC 对象的属性
                            rc = client.call("ak.wwise.core.object.get", {
                                "from": {"id": [ro["id"]]},
                                "options": {"return": ["name", "type", "path", "id"]}
                            })
                            print(f"  RTPC 对象详情: {rc}")
                break

    # -----------------------------------------------
    # 5. 查询所有类型的子对象（通过 descendants）
    # -----------------------------------------------
    print("\n=== 5. 查询 Sound 的所有后代（看 RTPC type） ===")
    r = client.call("ak.wwise.core.object.get", {
        "from": {"ofType": ["Sound"]},
        "transform": [{"select": ["descendants"]}],
        "options": {"return": ["name", "type", "path"]}
    })
    if r and r.get("return"):
        # 找非 AudioFileSource 类型的后代
        unique_types = list(set(o.get("type") for o in r["return"] if o.get("type") != "AudioFileSource"))
        print(f"  非 AudioFileSource 的后代类型: {unique_types}")
        # 如果有 Rtpc 类型
        rtpc_descendants = [o for o in r["return"] if "rtpc" in o.get("type","").lower()]
        if rtpc_descendants:
            print(f"  Rtpc 后代: {rtpc_descendants[:3]}")
        else:
            print("  没有找到 Rtpc 类型的后代")

    # -----------------------------------------------
    # 6. 尝试创建 Rtpc 对象作为 Sound 的子对象
    # -----------------------------------------------
    print("\n=== 6. 尝试 create Rtpc 作为子对象 ===")
    r = client.call("ak.wwise.core.object.create", {
        "name": "__test_rtpc__",
        "type": "Rtpc",
        "parent": sound_path,   # 字符串格式
        "onNameConflict": "replace"
    })
    print(f"  create Rtpc (string parent) -> {r}")

    # 6b. {"path": ...} 格式
    r = client.call("ak.wwise.core.object.create", {
        "name": "__test_rtpc2__",
        "type": "Rtpc",
        "parent": {"path": sound_path},
        "onNameConflict": "replace"
    })
    print(f"  create Rtpc ({{'path':...}} parent) -> {r}")

    # -----------------------------------------------
    # 7. 测试 setReference 是否有 RTPC 相关的 reference name
    # -----------------------------------------------
    print("\n=== 7. 测试 setReference 用于 RTPC ===")
    r = client.call("ak.wwise.core.object.setReference", {
        "object": {"path": sound_path},
        "reference": "Volume",
        "value": {"path": param_path}
    })
    print(f"  setReference Volume -> {r}")

    # -----------------------------------------------
    # 8. 测试 Effects - EffectSlot 创建
    # -----------------------------------------------
    print("\n=== 8. 测试 Effects 正确创建方式 ===")

    # 查询现有 EffectSlot 的 WAAPI 对象信息
    r = client.call("ak.wwise.core.object.get", {
        "from": {"ofType": ["EffectSlot"]},
        "options": {"return": ["name", "type", "path", "id"]}
    })
    if r and r.get("return"):
        print(f"  找到 {len(r['return'])} 个 EffectSlot")
        slot = r["return"][0]
        print(f"  第一个: {slot['path']}")
        # 查询其父节点
        parent_r = client.call("ak.wwise.core.object.get", {
            "from": {"path": [slot["path"]]},
            "transform": [{"select": ["parent"]}],
            "options": {"return": ["name", "type", "path"]}
        })
        if parent_r and parent_r.get("return"):
            print(f"  父节点: {[p.get('type') + ':' + p.get('path','?') for p in parent_r['return']]}")

        # 查询其子节点（Effect 对象）
        children_r = client.call("ak.wwise.core.object.get", {
            "from": {"id": [slot["id"]]},
            "transform": [{"select": ["children"]}],
            "options": {"return": ["name", "type", "path"]}
        })
        if children_r and children_r.get("return"):
            print(f"  子节点: {children_r['return'][:3]}")
    else:
        print("  没有找到 EffectSlot 对象")

    # -----------------------------------------------
    # 9. 尝试 create EffectSlot 用字符串 parent
    # -----------------------------------------------
    print("\n=== 9. 尝试 create EffectSlot（字符串 parent）===")
    r = client.call("ak.wwise.core.object.create", {
        "name": "__test_effectslot__",
        "type": "EffectSlot",
        "parent": sound_path,
        "onNameConflict": "replace"
    })
    print(f"  -> {r}")

    print("\n=== 测试完成 ===")
