# WwiseMCP 修复清单

## F-01 `set_rtpc_binding` WAAPI 调用无效

**文件**：`wwise_mcp/tools/action.py:269-273`
**严重程度**：高（工具实际调用时会失败）

**问题**：使用了非法的 WAAPI reference 名 `"Volume:RTPCController"`，该字段在 Wwise WAAPI 中不存在。

```python
# 当前错误实现
await adapter.set_reference(
    object_path,
    f"{property}:RTPCController",   # ← 非法 reference 名
    game_parameter_path,
)
```

**修复方向**：查阅 Wwise 2024.1 WAAPI 文档，确认 RTPC 绑定的正确接口（`ak.wwise.core.object.setProperty` 配合 RTPC 专属参数，或通过 `execute_waapi` 调用正确的 URI）。

---

## F-02 `add_effect` 路径逻辑错误

**文件**：`wwise_mcp/tools/action.py:319-325`
**严重程度**：高（工具实际调用时会报 WAAPI 错误）

**问题**：尝试在 `{object_path}\\Effects` 下创建效果器对象，但 Wwise 中不存在这样的虚拟子路径层级，WAAPI 会返回路径不存在错误。

```python
# 当前错误实现
await adapter.create_object(
    name=effect_name,
    obj_type=effect_type,
    parent_path=f"{object_path}\\Effects",   # ← Wwise 中不存在此路径
    ...
)
```

**修复方向**：查阅 Wwise 2024.1 WAAPI 中添加 Effect 的正确方式（通常通过 `ak.wwise.core.object.setReference` 或专用 Effect slot API）。

---

## F-03 动态上下文（System Prompt 区块 5）从未注入

**文件**：`wwise_mcp/server.py`
**严重程度**：中（功能缺失，RAG 系统完整实现但完全未接入）

**问题**：`build_dynamic_context()` 和 `WwiseRAG` 已完整实现，但 `server.py` 中从未调用，System Prompt 永远是纯静态内容，不符合设计方案第六章要求。

**修复方向**：在 MCP Prompt 注册中接入 `build_dynamic_context()`，或在工具调用前将动态上下文注入到返回内容中。

---

## F-04 `_warmup` 被错误注册为 MCP 工具

**文件**：`wwise_mcp/server.py:70-73`
**严重程度**：中（LLM 可见且可调用，调用后返回 None 而非 dict）

**问题**：内部初始化函数被 `@mcp.tool()` 装饰，暴露给了 LLM，且函数体为 `pass`，返回值类型与声明的 `dict` 不符。

```python
@mcp.tool()
async def _warmup() -> dict:
    pass   # ← 返回 None，不是 dict
```

**修复方向**：移除 `@mcp.tool()` 装饰器，使其仅作为内部函数。

---

## F-05 `set_property` 未调用 WwiseDocIndex 属性校验

**文件**：`wwise_mcp/tools/action.py:101-131`
**严重程度**：低（设计方案要求的防御性校验缺失）

**问题**：设计方案要求 `set_property` 调用前查 `WwiseDocIndex.is_valid_property()` 拦截非法属性名，`WwiseDocIndex` 已实现该方法，但 `set_property` 中从未调用。

**修复方向**：在 `set_property` 的批量循环中，对每个 `prop_name` 调用 `doc_index.is_valid_property()` 校验，不合法时提前返回含 suggestion 的错误。

---

## F-06 超时错误缺少一次自动重试

**文件**：`wwise_mcp/core/connection.py`
**严重程度**：低（设计方案错误处理表格明确要求）

**问题**：设计方案错误处理策略规定超时应做"1次自动重试"，当前实现直接抛出 `WwiseTimeoutError`，没有任何重试逻辑。

**修复方向**：在 `WwiseConnection.call()` 中，捕获 `WwiseTimeoutError` 后重试一次，第二次再超时才向上抛出。

---

## F-07 `requirements.txt` 含冗余依赖

**文件**：`requirements.txt`
**严重程度**：低（不影响功能，但会误导用户安装无用包）

**问题**：`asyncio-mqtt>=0.16.0` 在整个项目中没有任何使用，且未写入 `pyproject.toml`。

**修复方向**：从 `requirements.txt` 中移除该行。

---

---

## ~~F-08 连接层协议完全错误~~ ✅ 已修复

用 `waapi-client` 重写了 `connection.py` 和 `adapter.py`，字段名全部去掉 `@` 前缀，经实测验证通过。

---

## ~~F-09 所有 WAAPI 返回字段名带 `@` 前缀错误~~ ✅ 已修复

---

## F-08 连接层协议完全错误（最高优先级）

**文件**：`wwise_mcp/core/connection.py`、`wwise_mcp/core/adapter.py`
**严重程度**：致命（整个连接层无法工作）

**问题**：Wwise WAAPI 使用 WAMP 协议，不是普通 JSON-RPC WebSocket。当前 `connection.py` 手写的 JSON-RPC 实现与 Wwise 完全不兼容，MCP Server 启动后任何工具调用都会失败。

官方提供 `waapi-client` 库（`pip install waapi-client`）封装了完整的 WAMP 协议，应直接替换。

**正确调用方式（经实测验证）**：
```python
from waapi import WaapiClient

with WaapiClient() as client:
    result = client.call(
        "ak.wwise.core.object.get",
        {
            "from": {"ofType": ["GameParameter"]},
            "options": {"return": ["name", "path", "id", "type"]},
        },
    )
```

**修复方向**：用 `waapi-client` 重写 `connection.py` 和 `adapter.py`。

---

## F-09 所有 WAAPI 返回字段名带 `@` 前缀错误

**文件**：`wwise_mcp/tools/query.py`、`action.py`、`verify.py`、`rag/context_collector.py`
**严重程度**：致命（即使连接修好，所有查询结果都会解析失败）

**问题**：代码中大量使用 `"@name"`、`"@path"`、`"@id"`、`"@type"`、`"@childrenCount"` 作为返回字段名和结果解析 key。经实测，Wwise 2024.1 返回的字段名不带 `@` 前缀，是 `name`、`path`、`id`、`type`。

```python
# 当前错误写法
return_fields=["@name", "@type", "@path", "@id"]
obj.get("@name")

# 正确写法
"options": {"return": ["name", "type", "path", "id"]}
obj.get("name")
```

**修复方向**：全局替换所有 `@name`、`@path`、`@id`、`@type`、`@childrenCount`。

---

## 修复优先级

| 编号 | 问题 | 优先级 |
|---|---|---|
| F-08 | 连接层协议错误，需换 `waapi-client` | 致命 |
| F-09 | 返回字段名 `@` 前缀错误 | 致命 |
| F-01 | `set_rtpc_binding` WAAPI 调用无效 | 高 |
| F-02 | `add_effect` 路径错误 | 高 |
| F-03 | 动态上下文未注入 | 中 |
| F-04 | `_warmup` 错误注册为工具 | 中 |
| F-05 | `set_property` 缺少属性校验 | 低 |
| F-06 | 超时缺少自动重试 | 低 |
| F-07 | `requirements.txt` 冗余依赖 | 低 |
