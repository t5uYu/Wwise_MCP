# WwiseMCP

Wwise 2024.1 MCP Server — 让 AI 客户端（Claude Desktop、Cursor）通过自然语言操作 Wwise 项目。

## 前置条件

- **Wwise 2024.1** 已安装并运行，且已加载项目
- **WAAPI 已启用**：Edit → Preferences → Enable Wwise Authoring API (WAAPI)，端口默认 8080
- **Python 3.10+**

## 安装

```bash
git clone <仓库地址>
cd Wwise_Agent
pip install -e .
```

## 验证 WAAPI 连接

```bash
python check_waapi.py
```

连接成功后提示 Wwise 版本信息，即可继续配置 MCP 客户端。

## 配置 MCP 客户端

### Claude Desktop

编辑 `%APPDATA%\Claude\claude_desktop_config.json`：

```json
{
  "mcpServers": {
    "wwise": {
      "command": "wwise-mcp"
    }
  }
}
```

或使用项目路径模式（未全局安装时）：

```json
{
  "mcpServers": {
    "wwise": {
      "command": "python",
      "args": ["-m", "wwise_mcp.server"],
      "cwd": "D:/你的路径/Wwise_Agent"
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
      "cwd": "D:/你的路径/Wwise_Agent"
    }
  }
}
```

## 工具列表（17 个）

| 类别 | 工具 | 说明 |
|---|---|---|
| 查询 | `get_project_hierarchy` | 项目顶层结构概览 |
| 查询 | `get_object_properties` | 对象属性详情（分页） |
| 查询 | `search_objects` | 按关键词模糊搜索 |
| 查询 | `get_bus_topology` | Master-Mixer Bus 拓扑 |
| 查询 | `get_event_actions` | Event 下 Action 详情 |
| 查询 | `get_soundbank_info` | SoundBank 信息 |
| 查询 | `get_rtpc_list` | 所有 Game Parameter 列表 |
| 操作 | `create_object` | 创建 Wwise 对象 |
| 操作 | `set_property` | 设置对象属性（支持批量） |
| 操作 | `create_event` | 创建 Event + Action（三步自动完成） |
| 操作 | `assign_bus` | 将对象路由到指定 Bus |
| 操作 | `delete_object` | 删除对象（含引用安全检查） |
| 操作 | `move_object` | 移动对象到新父节点 |
| 验证 | `verify_structure` | 全项目结构完整性验证 |
| 验证 | `verify_event_completeness` | Event 触发链路验证 |
| 兜底 | `execute_waapi` | 直接执行原始 WAAPI 调用 |

## 已知限制（WAAPI 2024.1）

以下操作需在 Wwise 界面手动完成，API 不支持：

- **RTPC 绑定**：属性编辑器 → 右键属性 → Add RTPC
- **添加 Effect**：属性编辑器 → Effects 标签页
- **保存项目**：Ctrl+S 手动保存

## 详细文档

- [使用说明](docs/使用说明.md) — 场景示例、路径格式、常见问题
- [USER_GUIDE.md](docs/USER_GUIDE.md) — 英文版指南
