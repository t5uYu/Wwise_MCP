# WwiseMCP Server

Wwise 2024.1 AI Agent — 基于 WAAPI WebSocket + FastMCP 的 MCP Server

> 版本适配：Wwise 2024.1.x | UE5.4 | Python 3.10+

## 架构概览

```
Cursor / Claude Desktop
    ↕ MCP Protocol (stdio / SSE)
WwiseMCP Server (FastMCP)
    ↕ WAAPI WebSocket (JSON-RPC, ws://localhost:8080)
Wwise 2024.1 Authoring Tool
    ↕ Profiler Connection（可选）
UE5.4 Editor
```

## 前置条件

1. **Wwise 2024.1** 已安装并运行
2. 在 Wwise 中启用 WAAPI：`Project > User Settings > WAAPI > Enable WAAPI`（默认端口 8080）
3. Python 3.10+

## 安装

```bash
pip install -e .
# 或
pip install -r requirements.txt
```

## 启动

### stdio 模式（Cursor / Claude Desktop）

```bash
python -m wwise_mcp.server
# 或安装后：
wwise-mcp
```

### SSE 模式

```bash
wwise-mcp --transport sse --sse-port 8765
```

### 指定自定义 WAAPI 端口

```bash
wwise-mcp --host 127.0.0.1 --port 9090
```

## Cursor 配置

在项目根目录的 `.cursor/mcp.json` 中添加：

```json
{
  "mcpServers": {
    "wwise": {
      "command": "python",
      "args": ["-m", "wwise_mcp.server"],
      "cwd": "/path/to/Wwise_Agent"
    }
  }
}
```

## Claude Desktop 配置

在 `claude_desktop_config.json` 中添加：

```json
{
  "mcpServers": {
    "wwise": {
      "command": "python",
      "args": ["-m", "wwise_mcp.server"],
      "cwd": "/path/to/Wwise_Agent"
    }
  }
}
```

## 工具列表（19 个）

### 查询类（7 个）
| 工具 | 说明 |
|---|---|
| `tool_get_project_hierarchy` | 获取项目顶层结构概览 |
| `tool_get_object_properties` | 获取对象属性详情（支持分页） |
| `tool_search_objects` | 按关键词模糊搜索对象 |
| `tool_get_bus_topology` | 获取 Master-Mixer Bus 拓扑 |
| `tool_get_event_actions` | 获取 Event 下所有 Action 详情 |
| `tool_get_soundbank_info` | 获取 SoundBank 信息 |
| `tool_get_rtpc_list` | 获取所有 Game Parameter 列表 |

### 操作类（8 个）
| 工具 | 说明 |
|---|---|
| `tool_create_object` | 创建 Wwise 对象 |
| `tool_set_property` | 设置对象属性（支持批量） |
| `tool_create_event` | 创建 Event + Action（三步自动完成） |
| `tool_assign_bus` | 设置对象输出 Bus |
| `tool_set_rtpc_binding` | 绑定 RTPC 到属性 |
| `tool_add_effect` | 添加效果器 |
| `tool_delete_object` | 删除对象（含引用安全检查） |
| `tool_move_object` | 移动对象到新父节点 |

### 验证类（2 个）
| 工具 | 说明 |
|---|---|
| `tool_verify_structure` | 结构完整性验证 |
| `tool_verify_event_completeness` | Event 可触发性验证（2024.1 Auto-Defined Bank） |

### 兜底类（1 个）
| 工具 | 说明 |
|---|---|
| `tool_execute_waapi` | 直接执行原始 WAAPI 调用（含黑名单保护） |

## 典型工作流

**创建带 RTPC 音量控制的爆炸音效：**

```
1. tool_search_objects('Distance', type_filter='GameParameter')
2. tool_get_project_hierarchy()
3. tool_create_object('Explosion_SFX', 'Sound SFX', '\\Actor-Mixer Hierarchy\\Default Work Unit')
4. tool_create_event('Play_Explosion', 'Play', '\\Actor-Mixer Hierarchy\\Default Work Unit\\Explosion_SFX')
5. tool_set_rtpc_binding('...Explosion_SFX', 'Volume', '...Distance', 'Linear')
6. tool_verify_structure()
7. tool_verify_event_completeness('\\Events\\Default Work Unit\\Play_Explosion')
```

## 项目结构

```
wwise_mcp/
├── server.py                    # 入口：FastMCP 实例化 + 工具注册
├── core/
│   ├── adapter.py               # WwiseAdapter：WAAPI 调用封装
│   ├── connection.py            # 连接管理：重连、消息路由
│   └── exceptions.py            # 异常分类
├── tools/
│   ├── query.py                 # 查询类工具（7 个）
│   ├── action.py                # 操作类工具（8 个）
│   ├── verify.py                # 验证类工具（2 个）
│   └── fallback.py              # execute_waapi 兜底
├── rag/
│   ├── context_collector.py     # WwiseRAG：按需收集项目状态
│   └── doc_index.py             # WAAPI Schema + 知识库索引
├── prompts/
│   ├── system_prompt.py         # 固定区块 1-4（可缓存）
│   └── dynamic_context.py       # 动态上下文注入（区块 5）
├── config/
│   └── settings.py              # WAAPI 连接配置
└── doc/
    ├── waapi_schema_2024.1.json # WAAPI Schema
    └── knowledge_base.txt       # 音频设计知识库
```

# WwiseMCP 使用说明

> 适用版本：Wwise 2024.1 · Python 3.10+

WwiseMCP 是一个 MCP（Model Context Protocol）服务器，让你可以通过支持 MCP 的 AI 客户端（如 Claude Desktop、Cursor）用自然语言操作 Wwise 项目——搜索对象、修改属性、创建 Event、验证结构等，无需手动在 Wwise 界面逐项点击。

---

## 一、前置条件

| 条件 | 说明 |
|---|---|
| Wwise 2024.1 | 必须在 PC 上**打开**且**加载了项目** |
| WAAPI 已启用 | Wwise → Edit → Preferences → Enable SDK (WAAPI)，端口默认 **8080** |
| Python 3.10+ | `python --version` 确认 |
| MCP 客户端 | Claude Desktop 或 Cursor（任意支持 MCP 的客户端） |

---

## 二、安装

```bash
# 克隆或下载项目
git clone <仓库地址>
cd wwise_mcp

# 安装依赖（建议使用虚拟环境）
pip install -r requirements.txt

# 或直接安装为可执行命令
pip install -e .
```

---

## 三、配置 MCP 客户端

### Claude Desktop

编辑配置文件：
- Windows：`%APPDATA%\Claude\claude_desktop_config.json`
- macOS：`~/Library/Application Support/Claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "wwise": {
      "command": "python",
      "args": ["-m", "wwise_mcp.server"],
      "cwd": "D:/你的项目路径/Wwise_Agent"
    }
  }
}
```

如果已执行 `pip install -e .`，可用可执行命令替代：

```json
{
  "mcpServers": {
    "wwise": {
      "command": "wwise-mcp"
    }
  }
}
```

### Cursor

在项目根目录创建 `.cursor/mcp.json`：

```json
{
  "mcpServers": {
    "wwise": {
      "command": "python",
      "args": ["-m", "wwise_mcp.server"],
      "cwd": "D:/你的项目路径/Wwise_Agent"
    }
  }
}
```

### 自定义连接参数

如果 Wwise 不在默认端口（8080），可在启动参数中指定：

```json
"args": ["-m", "wwise_mcp.server", "--host", "127.0.0.1", "--port", "8080"]
```

---

## 四、启动与验证

1. **先打开 Wwise 并加载项目**
2. 重启 MCP 客户端（Claude Desktop / Cursor）
3. 在对话中提问，例如：

   > 帮我看一下这个 Wwise 项目有哪些顶层层级？

   如果工具正常连接，AI 会自动调用 `get_project_hierarchy` 并返回项目结构。

---

## 五、工具一览（19 个）

### 查询工具（7 个）

| 工具 | 用途 |
|---|---|
| `get_project_hierarchy` | 查看项目顶层结构概览（层级类型、子对象数量） |
| `search_objects` | 按关键词模糊搜索对象，支持类型过滤 |
| `get_object_properties` | 查看指定对象的所有属性（分页） |
| `get_event_actions` | 查看 Event 下所有 Action 及其 Target |
| `get_bus_topology` | 查看 Master-Mixer Bus 路由拓扑 |
| `get_soundbank_info` | 查看 SoundBank 信息 |
| `get_rtpc_list` | 查看所有 Game Parameter 及其范围和默认值 |

### 操作工具（8 个）

| 工具 | 用途 |
|---|---|
| `create_object` | 在指定父节点下创建对象（Sound、Event、Bus、Container 等） |
| `set_property` | 设置对象属性（Volume、Pitch、LowPassFilter 等），支持批量 |
| `create_event` | 一步创建 Event → Action → Target 完整链路 |
| `assign_bus` | 将 Sound/Container 路由到指定 Bus |
| `move_object` | 移动对象到新父节点 |
| `delete_object` | 删除对象，默认先检查引用再删除 |
| `set_rtpc_binding` | ⚠️ WAAPI 2024.1 不支持，会返回手动操作指引 |
| `add_effect` | ⚠️ WAAPI 2024.1 不支持，会返回手动操作指引 |

### 验证工具（2 个）

| 工具 | 用途 |
|---|---|
| `verify_structure` | 全项目（或指定范围）结构完整性检查 |
| `verify_event_completeness` | 验证指定 Event 的触发链路是否完整 |

### 兜底工具（1 个）

| 工具 | 用途 |
|---|---|
| `execute_waapi` | 直接透传任意 WAAPI 调用（危险操作已黑名单屏蔽） |

---

## 六、典型使用场景

### 场景 1：了解项目结构

```
你：帮我看一下这个 Wwise 项目有哪些主要层级，以及 Event 有多少个？
```

AI 会调用 `get_project_hierarchy`，返回各层级的子对象数量，包括 Events 层级的总数。

---

### 场景 2：搜索并查看音效属性

```
你：搜索一下名字带 "footstep" 的 Sound 对象，然后看看第一个的属性。
```

AI 先调用 `search_objects("footstep", type_filter="Sound")`，再调用 `get_object_properties` 查看属性列表。

---

### 场景 3：批量调整音量

```
你：把 \Actor-Mixer Hierarchy\Default Work Unit\UI_Click 的 Volume 调到 -12 dB，Pitch 设为 0。
```

AI 调用 `set_property`，批量写入 `{"Volume": -12.0, "Pitch": 0.0}`。

---

### 场景 4：创建新的 Event

```
你：为 \Actor-Mixer Hierarchy\Default Work Unit\Explosion_SFX 创建一个播放 Event，命名为 Play_Explosion。
```

AI 调用 `create_event("Play_Explosion", "Play", "<Sound 路径>")`，自动完成 Event → Action → Target 三步关联。

---

### 场景 5：检查项目健康度

```
你：帮我做一次全项目结构验证，看看有没有孤立的 Event 或者没挂 Bus 的 Sound。
```

AI 调用 `verify_structure()`，返回错误和警告列表。

---

### 场景 6：验证某个 Event 能否正常触发

```
你：验证一下 \Events\Enemies\EvilHead\Enemy_EvilHead_Hover_Play 这个 Event 能不能正常触发。
```

AI 调用 `verify_event_completeness`，逐项检查 Event → Action → Target → AudioFileSource → SoundBank 链路。

---

## 七、路径格式说明

Wwise 中所有路径以 `\` 开头，层级之间用 `\` 分隔：

```
\Actor-Mixer Hierarchy\Default Work Unit\MySound
\Events\Default Work Unit\Play_MySound
\Master-Mixer Hierarchy\Default Work Unit\Master Audio Bus\SFX
\Game Parameters\Default Work Unit\Distance
```

**注意**：向 AI 描述路径时，直接写中文描述即可（如"Events 层级下 Default Work Unit 里的 Play_Explosion"），AI 会自动推断完整路径格式。如果 AI 找不到，可要求先调用 `search_objects` 搜索。

---

## 八、已知限制（WAAPI 2024.1）

以下操作在当前 Wwise 2024.1 WAAPI 中**无法通过 API 实现**，需在 Wwise 界面手动操作：

| 操作 | 原因 | 替代方案 |
|---|---|---|
| 创建 RTPC 绑定 | API 不支持创建 Rtpc 类型对象 | Wwise 属性编辑器 → 右键属性 → Add RTPC |
| 添加 Effect | EffectSlot 不可通过 API 创建 | Wwise 属性编辑器 → Effects 标签页 |
| 保存项目 | 被安全黑名单屏蔽 | Ctrl+S 手动保存 |

---

## 九、安全机制

`execute_waapi` 工具支持直接执行任意 WAAPI 调用，但以下 URI 被永久屏蔽：

- `ak.wwise.core.project.open/close/save`
- `ak.wwise.ui.project.open`
- `ak.wwise.core.remote.connect/disconnect`
- `ak.wwise.core.undo.beginGroup`

AI 无法通过该工具触发项目关闭、远程连接等高风险操作。

---

## 十、常见问题

**Q：AI 说连接不上 Wwise？**
确认 Wwise 已打开且加载了项目，Edit → Preferences → Enable SDK (WAAPI) 已勾选，端口与配置中一致。

**Q：搜索时找不到对象？**
Wwise 路径区分大小写。可尝试只输入部分名称，`search_objects` 支持模糊匹配。

**Q：assign_bus 失败？**
Bus 路径需要包含完整路径，通常是 `\Master-Mixer Hierarchy\Default Work Unit\Master Audio Bus\...`，可先调用 `get_bus_topology` 获取正确路径。

**Q：操作后 Wwise 没有变化？**
确认 AI 工具调用返回 `"success": true`。如有疑问，可在 Wwise 的 Undo 历史中查看是否有操作记录。

