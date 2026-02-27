"""
测试脚本：验证 F-01 (set_rtpc_binding) 和 F-02 (add_effect) 的正确 WAAPI 接口
"""
import json
from waapi import WaapiClient

def pp(obj):
    print(json.dumps(obj, indent=2, ensure_ascii=False, default=str))

with WaapiClient() as client:

    # 获取一个 Sound 对象和 GameParameter 用于测试
    sounds = client.call("ak.wwise.core.object.get", {
        "from": {"ofType": ["Sound"]},
        "options": {"return": ["name", "path", "id"]}
    })
    sound = sounds["return"][0]
    print(f"测试 Sound: {sound['path']}")

    params = client.call("ak.wwise.core.object.get", {
        "from": {"ofType": ["GameParameter"]},
        "options": {"return": ["name", "path", "id"]}
    })
    param = params["return"][0]
    print(f"测试 GameParameter: {param['path']}")

    # -----------------------------------------------
    # 1. 查询 Sound 的属性/引用名称列表
    # -----------------------------------------------
    print("\n--- 1. getPropertyAndReferenceNames ---")
    try:
        names = client.call("ak.wwise.core.object.getPropertyAndReferenceNames", {
            "object": {"path": sound["path"]}
        })
        pp(names)
    except Exception as e:
        print(f"  失败: {e}")

    # -----------------------------------------------
    # 2. 测试 ak.wwise.core.object.addObjectToList（RTPC）
    # -----------------------------------------------
    print("\n--- 2. addObjectToList RTPC (结构一：properties+references) ---")
    try:
        result = client.call("ak.wwise.core.object.addObjectToList", {
            "id": {"path": sound["path"]},
            "listName": "RTPC",
            "child": {
                "type": "Rtpc",
                "properties": {
                    "PropertyName": "Volume"
                },
                "references": {
                    "ControlInput": {"path": param["path"]}
                }
            }
        })
        print("成功！")
        pp(result)
    except Exception as e:
        print(f"  失败: {e}")

    # -----------------------------------------------
    # 3. 测试 RTPC 结构二（扁平）
    # -----------------------------------------------
    print("\n--- 3. addObjectToList RTPC (结构二：扁平属性) ---")
    try:
        result = client.call("ak.wwise.core.object.addObjectToList", {
            "id": {"path": sound["path"]},
            "listName": "RTPC",
            "child": {
                "type": "Rtpc",
                "PropertyName": "Volume",
                "ControlInput": {"path": param["path"]}
            }
        })
        print("成功！")
        pp(result)
    except Exception as e:
        print(f"  失败: {e}")

    # -----------------------------------------------
    # 4. 测试 RTPC 结构三（使用 @type 等）
    # -----------------------------------------------
    print("\n--- 4. addObjectToList RTPC (结构三：使用id直接引用) ---")
    try:
        result = client.call("ak.wwise.core.object.addObjectToList", {
            "id": {"path": sound["path"]},
            "listName": "RTPC",
            "child": {
                "type": "Rtpc",
                "references": {
                    "PropertyName": "Volume",
                    "ControlInput": {"path": param["path"]}
                }
            }
        })
        print("成功！")
        pp(result)
    except Exception as e:
        print(f"  失败: {e}")

    # -----------------------------------------------
    # 5. 检查现有 Sound 的 RTPC bindings（如有）
    # -----------------------------------------------
    print("\n--- 5. 查询已有 RTPC 绑定的 Sound ---")
    try:
        # 查询有 RTPC 绑定的 Sound（通过 children 返回）
        sounds_with_rtpc = client.call("ak.wwise.core.object.get", {
            "from": {"ofType": ["Sound"]},
            "options": {"return": ["name", "path", "id", "type"]}
        })
        # 取前5个
        for s in sounds_with_rtpc["return"][:5]:
            print(f"  Sound: {s['path']}")
            # 查询该Sound的子对象（RTPC是否作为子对象存在）
            try:
                children = client.call("ak.wwise.core.object.get", {
                    "from": {"path": [s["path"]]},
                    "transform": [{"select": ["children"]}],
                    "options": {"return": ["name", "type", "path"]}
                })
                if children.get("return"):
                    print(f"    子对象: {[c.get('type','?') + ':' + c.get('name','?') for c in children['return']]}")
            except Exception as e2:
                print(f"    查询子对象失败: {e2}")
    except Exception as e:
        print(f"  失败: {e}")

    # -----------------------------------------------
    # 6. 直接在 Enemies_EvilHead.wwu 里找一个有 RTPC 绑定的 Sound 并查询其 children
    # -----------------------------------------------
    print("\n--- 6. 查询已知有 RTPC 绑定的 Sound 的子对象类型 ---")
    try:
        # 从 Enemies_EvilHead 获取有 RTPC 的 sound（EvilHead的movementspeed绑定）
        sounds_eh = client.call("ak.wwise.core.object.get", {
            "from": {"ofType": ["Sound"]},
            "where": [["name", "contains", "EvilHead"]],
            "options": {"return": ["name", "path", "id"]}
        })
        for s in sounds_eh.get("return", [])[:3]:
            print(f"  Sound: {s['path']}")
            try:
                children = client.call("ak.wwise.core.object.get", {
                    "from": {"path": [s["path"]]},
                    "transform": [{"select": ["children"]}],
                    "options": {"return": ["name", "type", "path"]}
                })
                print(f"    返回: {children}")
            except Exception as e2:
                print(f"    查询子对象失败: {e2}")
    except Exception as e:
        print(f"  失败: {e}")

    # -----------------------------------------------
    # 7. 测试 Effects addObjectToList
    # -----------------------------------------------
    print("\n--- 7. addObjectToList Effects (EffectSlot) ---")
    try:
        result = client.call("ak.wwise.core.object.addObjectToList", {
            "id": {"path": sound["path"]},
            "listName": "Effects",
            "child": {
                "type": "EffectSlot",
                "references": {
                    "Effect": {
                        "type": "PluginShareSet",
                        "name": "__test_effect__"
                    }
                }
            }
        })
        print("成功！")
        pp(result)
    except Exception as e:
        print(f"  失败: {e}")

    # -----------------------------------------------
    # 8. 测试 create 一个 EffectSlot 作为子对象（如果是这种方式）
    # -----------------------------------------------
    print("\n--- 8. create EffectSlot 作为 Sound 的子对象 ---")
    try:
        result = client.call("ak.wwise.core.object.create", {
            "name": "__test_effect_slot__",
            "type": "EffectSlot",
            "parent": {"path": sound["path"]},
            "onNameConflict": "fail"
        })
        print("成功！")
        pp(result)
    except Exception as e:
        print(f"  失败: {e}")

    print("\n=== 测试完成 ===")
