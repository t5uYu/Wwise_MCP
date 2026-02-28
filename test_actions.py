import sys, asyncio
sys.stdout.reconfigure(encoding='utf-8')

from wwise_mcp.core.adapter import init_connection
from wwise_mcp.tools.action import (
    create_object, set_property, create_event,
    assign_bus, delete_object, move_object,
)
from wwise_mcp.tools.query import get_object_properties

PARENT        = "\\Actor-Mixer Hierarchy\\Default Work Unit"
EVENTS_PARENT = "\\Events\\Default Work Unit"
MASTER_BUS    = "\\Master-Mixer Hierarchy\\Default Work Unit\\Master Audio Bus"
TEST_SOUND    = "MCP_TEST_Sound_DELETE_ME"
TEST_SOUND2   = "MCP_TEST_Move_DELETE_ME"
TEST_EVENT    = "MCP_TEST_Event_DELETE_ME"

def ok(r):  return r.get("success") is True

def show(label, r):
    if ok(r):
        print("    [OK]   " + label)
    else:
        print("    [FAIL] " + label + ": " + str(r.get("error")))
    return r

async def run():
    conn = init_connection()
    await conn.ensure_connected()

    created = []

    # 1. create_object
    print("\n[1] create_object (Sound SFX) ...")
    r = await create_object(TEST_SOUND, "Sound SFX", PARENT)
    show("create_object", r)
    print("    raw data = " + str(r.get("data")))
    sound_path = r.get("data", {}).get("path") if ok(r) else None
    if sound_path:
        created.append(sound_path)
        print("    path = " + sound_path)

    # 2. set_property
    if sound_path:
        print("\n[2] set_property Volume=-6, Pitch=200 ...")
        r = await set_property(sound_path, properties={"Volume": -6.0, "Pitch": 200.0})
        show("set_property", r)
        if ok(r):
            for item in r.get("data", {}).get("results", []):
                s = "OK" if item["success"] else "FAIL"
                print("    " + item["property"] + "=" + str(item["value"]) + " -> " + s)

    # 3. get_object_properties (verify)
    if sound_path:
        print("\n[3] get_object_properties (verify) ...")
        r = await get_object_properties(sound_path)
        if ok(r):
            obj = r["data"]["object"]
            total = r["data"]["pagination"]["total_properties"]
            print("    [OK]   name=" + str(obj.get("name")) + " type=" + str(obj.get("type")))
            print("    prop_count=" + str(total))
        else:
            print("    [FAIL] " + str(r.get("error")))

    # 4. create_event
    event_path = None
    if sound_path:
        print("\n[4] create_event Play targeting sound ...")
        r = await create_event(TEST_EVENT, "Play", sound_path, EVENTS_PARENT)
        show("create_event", r)
        if ok(r):
            event_path = r["data"]["event"]["path"]
            created.append(event_path)
            print("    event  = " + event_path)
            print("    action = " + r["data"]["action"]["path"])

    # 5. assign_bus
    if sound_path:
        print("\n[5] assign_bus to Master Audio Bus ...")
        r = await assign_bus(sound_path, MASTER_BUS)
        show("assign_bus", r)

    # 6. move_object
    print("\n[6] create & move object ...")
    r = await create_object(TEST_SOUND2, "Sound SFX", PARENT)
    show("create (move src)", r)
    move_src = r.get("data", {}).get("path") if ok(r) else None
    if move_src:
        created.append(move_src)
        r2 = await move_object(move_src, PARENT)
        show("move_object", r2)
        if ok(r2):
            new_path = r2["data"]["new_path"]
            if new_path not in created:
                created.append(new_path)

    # 7. cleanup
    print("\n[7] cleanup (delete all created objects) ...")
    for path in reversed(created):
        r = await delete_object(path, force=True)
        name = path.split("\\")[-1]
        status = "OK" if ok(r) else str(r.get("error", {}).get("message", "?"))
        print("    delete '" + name + "' -> " + status)

    await conn.close()
    print("\n=== Done ===")

asyncio.run(run())
