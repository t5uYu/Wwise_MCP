# WwiseMCP 修复清单 v2（最新进度）

> 本文档在 FIXES.md 基础上更新，反映当前实际测试结果。

---

## 已修复 ✅

### ~~F-07~~ ✅ `requirements.txt` 冗余依赖
`asyncio-mqtt` 已移除，`websockets` 替换为 `waapi-client`。

### ~~F-08~~ ✅ 连接层协议完全错误
用 `waapi-client` 完整重写了 `connection.py` 和 `adapter.py`，WAMP 协议问题已解决。经实测验证：24 个 GameParameter、174 个 Event、517 个 Sound 均可正常返回。

### ~~F-09~~ ✅ 所有 WAAPI 返回字段名带 `@` 前缀错误
全局替换了 `@name`→`name`、`@path`→`path`、`@id`→`id`、`@type`→`type`、`@childrenCount`→`childrenCount`，涉及 `query.py`、`action.py`、`verify.py`、`context_collector.py`、`doc_index.py`。

---

## 待修复

### F-10 adapter.py 写操作 object 参数格式错误（新发现，高优先级）

**文件**：`wwise_mcp/core/adapter.py`
**严重程度**：高（所有写操作实际上都会失败）

**问题**：adapter.py 中所有写操作（set_property、create_object、delete_object、move_object、set_reference）对 `object`/`parent` 参数使用了 `{"path": "..."}` 封装格式，但 WAAPI 2024.1 的 `objectArg` 类型不接受此格式。

**实测错误**：
```
ArgumentError: object={"path":"\\Actor-Mixer Hierarchy\\..."} does not match requirements.
schemaExpect: [uniqueQualifiedName, guid, objectPathArg]
```

**正确格式**（实测验证）：
```python
# 错误（当前）
"object": {"path": object_path}

# 正确：直接传路径字符串
"object": object_path

# 也正确：传 GUID
"object": object_guid
```

**受影响的 adapter 方法**：
- `create_object` → `"parent": {"path": parent_path}` 需改为 `"parent": parent_path`
- `set_property` → `"object": {"path": object_path}` 需改为 `"object": object_path`
- `set_reference` → `"object": {"path": object_path}` 和 `"value": {"path": value_path}` 均需改
- `delete_object` → `"object": {"path": object_path}` 需改为 `"object": object_path`
- `move_object` → `"object"` 和 `"parent"` 均需改

**注意**：`ak.wwise.core.object.get` 的 `from` 参数（如 `{"path": [...]}`、`{"ofType": [...]}` ）是 `fromSpec` 类型，与 `objectArg` 不同，不受此影响，保持不变。

---

### F-01 `set_rtpc_binding` WAAPI 调用无效（高）

**文件**：`wwise_mcp/tools/action.py:269-273`

**当前错误实现**：
```python
await adapter.set_reference(
    object_path,
    f"{property}:RTPCController",   # ← 非法 reference 名
    game_parameter_path,
)
```

**研究进展**：
- `ak.wwise.core.object.addObjectToList` —— **不存在**于 WAAPI 2024.1，返回 `invalid_procedure_uri`
- WAG 项目 XML 分析：RTPC 绑定在 XML 中存储为 Sound 的 `ObjectLists/ObjectList[@Name='RTPC']` 下的 `<RTPC>` 子元素，RTPC 对象自身有 GUID 和 ShortID，说明它是**可寻址的 WAAPI 对象**
- RTPC 子对象结构：`PropertyName=Volume`，`ControlInput` 引用指向 GameParameter
- 下一步：确认是否可以通过 `ak.wwise.core.object.create` 将 Rtpc 类型对象直接创建为 Sound 的子节点

**修复方向（待验证）**：
```python
# 候选方案：将 Rtpc 作为子对象创建
await adapter.create_object(
    name="",
    obj_type="Rtpc",
    parent_path=object_path,   # 修复 F-10 后使用字符串格式
    ...
)
# 然后 setProperty 设置 PropertyName
# 然后 setReference 设置 ControlInput
```

---

### F-02 `add_effect` 路径逻辑错误（高）

**文件**：`wwise_mcp/tools/action.py:319-325`

**当前错误实现**：
```python
await adapter.create_object(
    ...
    parent_path=f"{object_path}\\Effects",   # ← 不存在此路径
)
```

**研究进展**：
- WAG 项目 XML 分析：Effects 在 XML 中存储为 Sound 的 `ObjectLists/ObjectList[@Name='Effects']` 下的 `<EffectSlot>` 子元素
- WAAPI 查询 `{"ofType": ["EffectSlot"]}` 可以返回所有 EffectSlot 对象，说明 EffectSlot 是可查询的 WAAPI 对象类型
- `addObjectToList` 不可用
- 下一步：测试 `ak.wwise.core.object.create` 能否以 Sound 为父节点创建 EffectSlot

**修复方向（待验证）**：
```python
# 候选方案：将 EffectSlot 作为子对象创建
await adapter.create_object(
    name="",
    obj_type="EffectSlot",
    parent_path=object_path,  # 修复 F-10 后使用字符串格式
    ...
)
# 然后 setReference 设置 Effect 引用到 ShareSet
```

---

### F-04 `_warmup` 被错误注册为 MCP 工具（中）

**文件**：`wwise_mcp/server.py:70-73`

**问题**：
```python
@mcp.tool()
async def _warmup() -> dict:
    pass   # ← 返回 None，且不应对外暴露
```

**修复**：移除 `@mcp.tool()` 装饰器，改为在 `main()` 或 lifespan 中调用 `_ensure_connection()`。

---

### F-03 动态上下文（System Prompt 区块 5）从未注入（中）

**文件**：`wwise_mcp/server.py`

**问题**：`build_dynamic_context()` 和 `WwiseRAG` 已完整实现，但从未在 server.py 中调用，System Prompt 始终是纯静态内容。

**修复方向**：在 `get_system_prompt()` 资源函数中调用 `build_dynamic_context()`，将动态上下文追加到 STATIC_SYSTEM_PROMPT 后面。

---

### F-05 `set_property` 未调用 WwiseDocIndex 属性校验（低）

**文件**：`wwise_mcp/tools/action.py:101-131`

**修复方向**：在批量循环中对每个 `prop_name` 调用 `doc_index.is_valid_property()` 校验，不合法时返回含 suggestion 的错误。

---

### F-06 超时错误缺少一次自动重试（低）

**文件**：`wwise_mcp/core/connection.py`

**修复方向**：在 `call()` 中捕获超时异常后重试一次，第二次再超时才向上抛出。

---

## 修复优先级（更新版）

| 编号 | 问题 | 优先级 | 状态 |
|---|---|---|---|
| F-10 | adapter.py 写操作 object 格式错误 | 高 | 待修复 |
| F-01 | `set_rtpc_binding` WAAPI 接口错误 | 高 | 研究中 |
| F-02 | `add_effect` 路径错误 | 高 | 研究中 |
| F-04 | `_warmup` 误注册为 MCP 工具 | 中 | 待修复 |
| F-03 | 动态上下文未注入 | 中 | 待修复 |
| F-05 | `set_property` 缺属性校验 | 低 | 待修复 |
| F-06 | 超时缺少自动重试 | 低 | 待修复 |
| ~~F-07~~ | ~~requirements.txt 冗余依赖~~ | - | ✅ 已修复 |
| ~~F-08~~ | ~~连接层协议错误~~ | - | ✅ 已修复 |
| ~~F-09~~ | ~~字段名 @ 前缀错误~~ | - | ✅ 已修复 |

---

## 下一步行动

1. **立即可做**：修复 F-10（adapter.py 参数格式）+ F-04（_warmup 误注册）
2. **需要测试**：继续 F-01/F-02 的 RTPC/Effect 创建方式验证
3. **顺序修复**：F-10 修完后 F-01/F-02 的 adapter 调用也要同步更新格式
