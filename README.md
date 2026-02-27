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
