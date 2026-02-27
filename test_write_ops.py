"""
测试 F-10 修复：验证写操作参数格式，同时测 F-01/F-02 正确接口
"""
import json
from waapi import WaapiClient

def pr(label, val):
    print(f"  [{label}] -> {json.dumps(val, ensure_ascii=False, default=str) if val is not None else 'None (FAIL)'}")

with WaapiClient() as client:

    # 基础数据
    sounds = client.call("ak.wwise.core.object.get", {
        "from": {"ofType": ["Sound"]},
        "options": {"return": ["name", "path", "id"]}
    })
    sound = sounds["return"][0]
    sound_path = sound["path"]

    params = client.call("ak.wwise.core.object.get", {
        "from": {"ofType": ["GameParameter"]},
        "options": {"return": ["name", "path", "id"]}
    })
    param = params["return"][0]
    param_path = param["path"]

    print(f"Sound: {sound_path}")
    print(f"Param: {param_path}")

    # -----------------------------------------------
    # F-10 验证：setProperty / setReference 字符串格式
    # -----------------------------------------------
    print("\n=== F-10: setProperty (string object) ===")
    r = client.call("ak.wwise.core.object.setProperty", {
        "object": sound_path,
        "property": "Volume",
        "value": -3.0
    })
    pr("setProperty Volume=-3", r)

    print("\n=== F-10: setReference (string object + string value) ===")
    # 先找一个 Bus 路径
    buses = client.call("ak.wwise.core.object.get", {
        "from": {"ofType": ["Bus"]},
        "options": {"return": ["name", "path", "id"]}
    })
    if buses and buses.get("return"):
        bus_path = buses["return"][0]["path"]
        print(f"  Bus: {bus_path}")
        r = client.call("ak.wwise.core.object.setReference", {
            "object": sound_path,
            "reference": "OutputBus",
            "value": bus_path
        })
        pr("setReference OutputBus", r)

    # -----------------------------------------------
    # F-10 验证：create_object (string parent)
    # -----------------------------------------------
    print("\n=== F-10: create_object (string parent) ===")
    # 找一个 WorkUnit 作为父节点
    wus = client.call("ak.wwise.core.object.get", {
        "from": {"ofType": ["WorkUnit"]},
        "options": {"return": ["name", "path", "id"]}
    })
    # 找 Actor-Mixer 下的 Default Work Unit
    wu = next((w for w in wus.get("return", [])
               if "Actor-Mixer" in w.get("path","") and w.get("name") == "Default Work Unit"), None)
    if wu:
        wu_path = wu["path"]
        print(f"  Parent WorkUnit: {wu_path}")
        r = client.call("ak.wwise.core.object.create", {
            "name": "__test_sound_f10__",
            "type": "Sound",
            "parent": wu_path,
            "onNameConflict": "replace"
        })
        pr("create Sound", r)
        test_sound_path = r.get("path") if r else None

        if test_sound_path:
            # -----------------------------------------------
            # F-01 测试：用 create 创建 Rtpc 子对象
            # -----------------------------------------------
            print("\n=== F-01: create Rtpc as child of Sound ===")
            r = client.call("ak.wwise.core.object.create", {
                "name": "__test_rtpc__",
                "type": "Rtpc",
                "parent": test_sound_path,
                "onNameConflict": "replace"
            })
            pr("create Rtpc child", r)

            if r and r.get("path"):
                rtpc_path = r["path"]
                print(f"  Rtpc created at: {rtpc_path}")
                # 设置 PropertyName
                r2 = client.call("ak.wwise.core.object.setProperty", {
                    "object": rtpc_path,
                    "property": "PropertyName",
                    "value": "Volume"
                })
                pr("  setProperty PropertyName=Volume", r2)
                # 设置 ControlInput 引用
                r3 = client.call("ak.wwise.core.object.setReference", {
                    "object": rtpc_path,
                    "reference": "ControlInput",
                    "value": param_path
                })
                pr("  setReference ControlInput", r3)

            # -----------------------------------------------
            # F-02 测试：用 create 创建 EffectSlot 子对象
            # -----------------------------------------------
            print("\n=== F-02: create EffectSlot as child of Sound ===")
            r = client.call("ak.wwise.core.object.create", {
                "name": "__test_effectslot__",
                "type": "EffectSlot",
                "parent": test_sound_path,
                "onNameConflict": "replace"
            })
            pr("create EffectSlot child", r)

            if r and r.get("path"):
                slot_path = r["path"]
                print(f"  EffectSlot created at: {slot_path}")
                # 找一个已有 Effect ShareSet
                effects = client.call("ak.wwise.core.object.get", {
                    "from": {"ofType": ["Effect"]},
                    "options": {"return": ["name", "path", "id"]}
                })
                if effects and effects.get("return"):
                    eff = effects["return"][0]
                    print(f"  Existing Effect: {eff['path']}")
                    r4 = client.call("ak.wwise.core.object.setReference", {
                        "object": slot_path,
                        "reference": "Effect",
                        "value": eff["path"]
                    })
                    pr("  setReference Effect", r4)

            # 清理测试对象
            print("\n=== 清理测试对象 ===")
            r = client.call("ak.wwise.core.object.delete", {
                "object": test_sound_path
            })
            pr("delete test Sound", r)

    print("\n=== 测试完成 ===")
