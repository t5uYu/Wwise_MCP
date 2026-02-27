# Wwise 2024.1 AI Agent 接入技术设计方案

> 基于 WAAPI WebSocket + 6层通用架构
>
> 版本适配：Wwise 2024.1.x | UE5.4 | Python 3.10+

---

## 一、Wwise 2024.1 关键特性与技术选型依据

### 1.1 相较 2019 版本的核心变化

| 变化点 | 2019 版本 | 2024.1 版本 | 对 Agent 的影响 |
|---|---|---|---|
| SoundBank 管理 | 手动管理 Bank 加载/卸载 | Auto-Defined SoundBanks，Event 自动对应 Bank | 查询 API 结构简化，create_event 工具不需要再关联 Bank |
| WAAPI 覆盖范围 | 基础 CRUD，Blend Container 不支持 | 新增 Blend Track/Child 管理 API | 工具集可覆盖 Blend Container 操作 |
| Live Editing | 修改后需重新生成 SoundBank | 直接实时同步，无需重新 cook | Agent 操作结果即时可见，验证循环大幅提速 |
| 插件 GUI 架构 | AudioPlugin.h 旧接口 | 新 Plugin.h 接口（旧接口已移除） | 若需开发 Wwise 插件辅助 Agent，必须用新 API |
| UE 集成打包 | 独立文件 | Wwise 资产打包进 Unreal uasset | UE 端工具调用路径需适配新打包格式 |
| 多线程支持 | 单线程 | 非 Unity 集成新增多线程支持 | WAAPI 并发调用更稳定 |

### 1.2 部署模式选型：纯 MCP Server 模式

根据通用方案的两种部署模式对比，Wwise 接入选择**模式 B（纯 MCP Server）**，理由如下：

- WAAPI 本身是 WebSocket JSON-RPC 协议，无主线程限制，天然适合独立进程部署
- Wwise 没有类似 Blender/Houdini 的内嵌 Python 环境，不适合进程内 exec 模式
- 音频设计师工作流以 Cursor / Claude Desktop 为主力工具，MCP Server 模式接入成本最低
- 2024.1 的 Live Editing 使实时反馈成为可能，MCP Server 能充分利用这一特性

---

## 二、整体架构设计

### 2.1 系统拓扑

系统由四个进程组成，通过两条独立通道通信：

| 进程 | 技术栈 | 职责 |
|---|---|---|
| Wwise Authoring Tool | Wwise 2024.1 | 宿主，暴露 WAAPI WebSocket 端口（默认 :8080） |
| WwiseMCP Server | Python 3.10 + FastMCP + websockets | MCP 工具注册、WAAPI 代理、结构化返回 |
| Cursor / Claude Desktop | 外部 MCP Client | 承担 Agent Loop、LLM 通信、Function Calling 编排 |
| UE5.4 Editor（可选） | UE5.4 + Wwise Integration | 运行时验证，通过 Profiler 连接 Wwise 进行实时调试 |

通信链路：

```
Cursor / Claude Desktop
    ↕ MCP Protocol (stdio / SSE)
WwiseMCP Server (FastMCP)
    ↕ WAAPI WebSocket (JSON-RPC, ws://localhost:8080)
Wwise 2024.1 Authoring Tool
    ↕ Profiler Connection（可选，用于运行时验证）
UE5.4 Editor
```

### 2.2 六层架构映射

通用方案的 6 层架构在 Wwise 接入中的具体映射：

| 层级 | 通用抽象 | Wwise 具体实现 |
|---|---|---|
| Layer 1 | Host Adapter | WwiseAdapter — WAAPI WebSocket 连接、JSON-RPC 请求封装、重连机制 |
| Layer 2 | RAG & Doc Index | WwiseRAG — 项目层级收集 + BusTopology；WwiseDocIndex — WAAPI Schema dict 索引 |
| Layer 3 | LLM Communication | 由外部 MCP Client 承担（Cursor / Claude Desktop） |
| Layer 4 | Tool System | 18 个预定义工具 + execute_waapi 兜底工具 |
| Layer 5 | Agent Core | 由外部 MCP Client 承担（Function Calling Loop） |
| Layer 6 | Domain Knowledge | Wwise 领域 System Prompt + WAAPI Schema 注入 |

---

## 三、Layer 1：WwiseAdapter 设计

### 3.1 WAAPI 连接层

WwiseAdapter 负责与 Wwise 2024.1 的 WAAPI 建立持久 WebSocket 连接，封装 JSON-RPC 调用格式。

#### 3.1.1 连接参数

| 参数 | 默认值 | 说明 |
|---|---|---|
| host | 127.0.0.1 | Wwise 运行的本机地址 |
| port | 8080 | WAAPI 默认端口，可在 Wwise User Settings 修改 |
| timeout | 10s | 单次请求超时 |
| reconnect_interval | 3s | 断线重连间隔 |
| max_reconnect | 5 | 最大重连次数，超出后返回错误而非无限等待 |

#### 3.1.2 核心接口

```python
class WwiseAdapter(IHostAdapter):
    async def call(self, uri: str, args: dict = {}, opts: dict = {}) -> dict:
        # 封装标准 WAAPI JSON-RPC 调用
        # uri: 如 'ak.wwise.core.object.get'
        # args: 业务参数
        # opts: 返回字段控制（@name, @type, @path 等）
        ...

    async def subscribe(self, uri: str, callback) -> int:
        # 订阅 WAAPI 事件（如对象变更通知）
        # 返回 subscription_id，用于后续取消订阅
        ...
```

### 3.2 2024.1 特有的 API 适配

Wwise 2024.1 新增或调整了以下 WAAPI 函数，WwiseAdapter 需做对应处理：

- Blend Container 系列 API 为 2024.1 新增，需在工具描述中注明版本要求
- `ak.wwise.core.object.setReference` 在 2024.1 中参数结构有调整，注意 platform 字段默认值变化
- SoundBank 相关的 `ak.wwise.core.soundbank.generate` 在 Auto-Defined SoundBank 场景下行为变化，LLM 需在 System Prompt 中明确

---

## 四、Layer 2：WwiseRAG 与文档索引设计

### 4.1 WwiseRAG：场景上下文收集

WwiseRAG 在每次 LLM 调用前收集必要的 Wwise 项目状态，注入 System Prompt 或用户消息。采用 Houdini Agent 的按需检索策略，避免全量收集导致 token 爆炸。

#### 4.1.1 收集内容与触发策略

| 上下文类型 | 收集方式 | 触发条件 | Token 估算 |
|---|---|---|---|
| 项目基础信息 | ak.wwise.core.getInfo | 每次会话初始化 | ~100 tokens |
| Actor-Mixer 层级概览 | ak.wwise.core.object.get（depth=2） | 用户消息含 Sound/Event 关键词 | ~300-500 tokens |
| Master-Mixer Bus 拓扑 | ak.wwise.core.object.get（type=Bus） | 用户消息含 Bus/Mix/Output 关键词 | ~200-400 tokens |
| 当前选中对象详情 | ak.wwise.ui.getSelectedObjects | 用户消息含 this/selected/当前 等指示词 | ~150 tokens |
| Event 列表概览 | ak.wwise.core.object.get（type=Event） | 用户消息含 Event/trigger/触发 关键词 | ~200-600 tokens |

### 4.2 WwiseDocIndex：WAAPI Schema 索引

将 Wwise 2024.1 的 WAAPI Schema（JSON 格式，官方 SDK 附带）预处理为 O(1) 查找的 dict 结构。

#### 4.2.1 索引结构

```python
# 索引格式：函数名 → {description, args_schema, return_schema}
waapi_index = {
    'ak.wwise.core.object.create': {
        'description': '在指定父对象下创建新对象',
        'required_args': ['name', 'type', 'parent', 'onNameConflict'],
        'optional_args': ['children', 'notes'],
        'return_fields': ['id', 'name', 'path', 'type'],
        'since': '2017.1'
    },
    # 2024.1 新增
    'ak.wwise.core.object.addChild': { ... },
    # ...
}
```

#### 4.2.2 额外知识库

除 WAAPI Schema 外，补充以下领域知识库（.txt 格式，关键词索引）：

- Wwise 对象层级关系：Event → Action → Target，Sound → AudioFileSource 等
- Bus 路由最佳实践：Master Audio Bus 结构、Side Chain 配置模式
- RTPC 绑定模式：Game Parameter → Volume/Pitch/LPF 典型配置
- SoundBank 策略：2024.1 Auto-Defined vs User-Defined 选择逻辑
- 2024.1 Breaking Changes 摘要：与旧版行为不一致的 API 清单

---

## 五、Layer 4：工具系统设计（18 + 1 个工具）

### 5.1 工具分类总览

| 分类 | 数量 | 工具列表 |
|---|---|---|
| 查询类（Query） | 7 | get_project_hierarchy, get_object_properties, search_objects, get_bus_topology, get_event_actions, get_soundbank_info, get_rtpc_list |
| 操作类（Action） | 8 | create_object, set_property, create_event, assign_bus, set_rtpc_binding, add_effect, delete_object, move_object |
| 验证类（Verify） | 2 | verify_structure, verify_event_completeness |
| 兜底类（Fallback） | 1 | execute_waapi |

### 5.2 查询类工具详细设计

#### get_project_hierarchy

| 字段 | 值 |
|---|---|
| WAAPI 映射 | ak.wwise.core.object.get（root: {path: '\\'}, return: @name,@type,@childrenCount） |
| 用途 | 获取项目顶层结构，供 LLM 理解当前项目规模和组织方式 |
| 返回示例 | `{ Actor-Mixer Hierarchy: 42 objects, Master-Mixer Hierarchy: 8 buses, Events: 156 }` |
| 2024.1 注意 | Auto-Defined SoundBank 场景下 SoundBanks 节点可能为空，属正常行为 |

#### get_object_properties

| 字段 | 值 |
|---|---|
| WAAPI 映射 | ak.wwise.core.object.get + ak.wwise.core.object.getPropertyAndReferenceNames |
| 输入参数 | object_path: str（支持 WAAPI 路径格式） |
| 返回字段 | @name, @type, @path, @id, Volume, Pitch, LPF, OutputBus, Positioning 等关键属性 |
| 分页策略 | 属性超过 30 个时自动分页，避免单次返回 token 过多 |

#### search_objects

| 字段 | 值 |
|---|---|
| WAAPI 映射 | ak.wwise.core.object.get（where 条件查询） |
| 输入参数 | query: str, type_filter: str（可选），max_results: int = 20 |
| 匹配策略 | name:contains 模糊匹配，结果按路径排序 |
| 用途 | LLM 不知道精确路径时，通过关键词定位目标对象 |

### 5.3 操作类工具详细设计

#### create_object

| 字段 | 值 |
|---|---|
| WAAPI 映射 | ak.wwise.core.object.create |
| 输入参数 | name: str, type: str, parent_path: str, on_conflict: str = 'rename' |
| 安全机制 | 创建前先调用 search_objects 检查同名对象是否存在，避免意外覆盖 |
| 2024.1 适配 | on_conflict 参数在 2024.1 中新增 'fail' 选项，Agent 默认使用 'rename' 保证安全 |
| 返回 | 新对象的 {id, name, path}，供后续操作工具链式调用 |

#### set_property

| 字段 | 值 |
|---|---|
| WAAPI 映射 | ak.wwise.core.object.setProperty 或 ak.wwise.core.object.setReference |
| 输入参数 | object_path: str, property: str, value: Union[float, str, bool], platform: str = None |
| 批量支持 | 接受 properties: dict 批量设置多个属性，内部串行调用减少 LLM 工具调用轮次 |
| 类型验证 | 调用前查 WwiseDocIndex 确认属性名合法性，非法属性名提前拦截返回明确错误 |

#### create_event

| 字段 | 值 |
|---|---|
| WAAPI 映射 | ak.wwise.core.object.create（type=Event）+ ak.wwise.core.object.create（type=Action） |
| 输入参数 | event_name: str, action_type: str（Play/Stop/Pause 等）, target_path: str |
| 流程 | 1. 创建 Event 对象  2. 在 Event 下创建 Action  3. 设置 Action 的 Target 引用 |
| 2024.1 优化 | 利用 Live Editing 特性，创建后无需生成 SoundBank 即可立即验证 Event 是否可触发 |

#### set_rtpc_binding

| 字段 | 值 |
|---|---|
| WAAPI 映射 | ak.wwise.core.object.setReference（将 Game Parameter 绑定到属性的 RTPC 曲线） |
| 输入参数 | object_path: str, property: str, game_parameter_path: str, curve_type: str = 'Linear' |
| 验证 | 绑定后调用 get_object_properties 确认 RTPC 节点已正确出现在对象属性树中 |

### 5.4 验证类工具详细设计

#### verify_structure

结构完整性验证，在 Agent 完成一轮操作后由 LLM 主动调用。

| 检查项 | WAAPI 实现 | 通过条件 |
|---|---|---|
| Event→Action 关联 | 遍历 Event 子节点，检查 Action 数量 | 每个 Event 至少有 1 个 Action |
| Action→Target 引用 | 检查 Action 的 Target 引用字段 | Target 引用非空且目标对象存在 |
| Bus 路由 | 检查 Sound 的 OutputBus 字段 | OutputBus 不为空，且目标 Bus 存在于 Master-Mixer 中 |
| 属性值范围 | 检查 Volume 是否在合理范围内 | Volume 在 -200dB ~ +200dB，Pitch 在 -2400 ~ +2400 |
| 孤立对象 | 查找无 Action 的 Event，无 OutputBus 的 Sound | 返回孤立对象列表供 LLM 决策 |

#### verify_event_completeness

专项验证：针对 Wwise 2024.1 的 Auto-Defined SoundBank 场景，验证 Event 是否可以被正常触发。

- 检查 Event 关联的所有 AudioFileSource 是否有对应的音频文件
- 检查 Auto-Defined SoundBank 是否已生成（ak.wwise.core.soundbank.getInclusions）
- 通过 Live Editing 连接验证 Event 是否可在 Profiler 中触发

### 5.5 兜底工具：execute_waapi

| 字段 | 值 |
|---|---|
| 功能 | 直接执行原始 WAAPI 调用，绕过预定义工具 |
| 输入参数 | uri: str, args: dict, opts: dict |
| 使用场景 | 预定义工具未覆盖的操作，或调试时需要精确控制 WAAPI 参数 |
| 安全限制 | 黑名单过滤：禁止调用 ak.wwise.core.project.open/close/save 等危险操作 |

---

## 六、Layer 6：Wwise 领域 System Prompt 设计

### 6.1 System Prompt 结构

System Prompt 分为 5 个固定区块，利用 Wwise 2024.1 / Claude 的 Prompt Cache 特性确保前缀稳定：

| 区块 | 内容 | Token 估算 | 缓存策略 |
|---|---|---|---|
| 1. 角色定义 | Wwise 音频设计专家角色，操作边界声明 | ~200 | 永久缓存 |
| 2. 对象模型 | Event→Action→Target 层级，Bus 路由架构，RTPC 系统说明 | ~800 | 永久缓存 |
| 3. 2024.1 特性 | Auto-Defined SoundBank 行为，Live Editing 使用方法，新增 API 说明 | ~400 | 永久缓存 |
| 4. 操作规范 | Undo 安全提示，命名规范，verify_structure 调用时机 | ~300 | 永久缓存 |
| 5. 动态上下文 | WwiseRAG 注入的项目状态（层级概览/当前选中对象） | ~200-600 | 不缓存 |

### 6.2 关键提示词规则

#### Auto-Defined SoundBank 规则

- 2024.1 项目默认开启 Auto-Defined SoundBank，不需要手动调用 SoundBank 生成工具
- User-Defined SoundBank 只在用户明确要求时才创建
- generate_soundbank 工具仅在用户明确要求打包/发布时调用

#### 操作顺序规则

- 创建 Event 必须按顺序：先创建 Event 对象 → 再创建 Action → 最后设置 Target 引用
- 删除对象前必须先调用 search_objects 确认无其他对象引用该目标
- 每完成一个独立操作目标后，必须调用 verify_structure 进行验证

#### Live Editing 利用规则

- 2024.1 的属性修改可实时反映到已连接的游戏实例，通知用户可在游戏中即时听到效果
- 如果 Profiler 已连接，操作后建议用户在游戏中验证，而不是依赖纯结构验证

---

## 七、代码组织结构

```
wwise_mcp/
├── server.py                    # 入口：FastMCP 实例化 + 工具注册 + 启动
├── core/
│   ├── adapter.py               # WwiseAdapter：WAAPI WebSocket 连接封装
│   ├── connection.py            # 连接管理：重连、心跳、订阅生命周期
│   └── exceptions.py            # WwiseAPIError / ConnectionError 分类
├── tools/
│   ├── query.py                 # 查询类工具（7个）
│   ├── action.py                # 操作类工具（8个）
│   ├── verify.py                # 验证类工具（2个）
│   └── fallback.py              # execute_waapi 兜底 + 黑名单过滤
├── rag/
│   ├── context_collector.py     # WwiseRAG：按需收集项目状态
│   └── doc_index.py             # WAAPI Schema + 知识库 dict 索引
├── prompts/
│   ├── system_prompt.py         # 固定区块 1-4（可缓存部分）
│   └── dynamic_context.py       # 动态上下文注入（区块 5）
├── config/
│   └── settings.py              # WAAPI host/port/timeout/黑名单配置
└── doc/
    ├── waapi_schema_2024.1.json # 官方 WAAPI Schema
    └── knowledge_base.txt       # 手工编写的音频设计知识库
```

---

## 八、错误处理策略

### 8.1 错误分类与处理

| 错误类型 | 来源 | 处理策略 | 是否重试 |
|---|---|---|---|
| WAAPI 调用失败 | Wwise 返回 error 字段 | 解析 error.message 返回给 LLM，LLM 决策是否修改参数重试 | LLM 决策 |
| 连接断开 | WebSocket 断线 | 自动重连（最多 5 次），重连失败后返回工具错误 | 自动重连 |
| 对象不存在 | get/set 操作目标路径无效 | 返回 not_found 结构化错误，建议 LLM 先调用 search_objects 定位 | 否 |
| 黑名单操作 | execute_waapi 触发黑名单 | 立即返回 forbidden 错误，不执行，记录日志 | 否 |
| 属性名非法 | set_property 参数校验失败 | 查 WwiseDocIndex 返回合法属性名列表供 LLM 修正 | 否 |
| 超时 | WAAPI 请求超时 | 返回 timeout 错误，提示用户检查 Wwise 是否运行 | 1次自动重试 |

### 8.2 结构化错误返回格式

```python
# 所有工具统一返回格式
{
    'success': bool,
    'data': dict | None,          # 成功时的返回数据
    'error': {
        'code': str,              # 'not_found' / 'invalid_param' / 'forbidden' 等
        'message': str,           # 人类可读的错误描述
        'suggestion': str | None  # 给 LLM 的修正建议
    } | None
}
```

---

## 九、实施路线

| 阶段 | 任务 | 产出 | 预估工时 |
|---|---|---|---|
| Phase 1 基础连接 | 实现 WwiseAdapter + 连接管理；验证 WAAPI 基础调用可用；FastMCP server 骨架 | 可连接 Wwise 的 MCP Server | 3-4 天 |
| Phase 2 查询工具 | 实现全部 7 个查询类工具；构建 WwiseDocIndex；编写初版 System Prompt | 可查询 Wwise 项目信息 | 3-4 天 |
| Phase 3 操作工具 | 实现全部 8 个操作类工具；2024.1 特性适配；execute_waapi 兜底 | 可执行完整的音频设计操作 | 5-6 天 |
| Phase 4 验证与 RAG | 实现验证类工具；WwiseRAG 按需收集；System Prompt 精调 | 完整的 Agent 闭环 | 3-4 天 |
| Phase 5 集成测试 | 与 Cursor / Claude Desktop 集成测试；覆盖典型场景；2024.1 Live Editing 验证流程测试 | 可交付的 MCP Server | 2-3 天 |

---

## 十、典型工作流示例

### 示例：创建一个带 RTPC 音量控制的 SFX Event

**用户指令：「帮我创建一个爆炸音效，音量随距离衰减，绑定到 Distance 这个 RTPC」**

| 步骤 | 工具调用 | 说明 |
|---|---|---|
| 1 | search_objects('Distance', type='GameParameter') | 确认 Distance 这个 Game Parameter 存在 |
| 2 | get_project_hierarchy() | 确认 Actor-Mixer 层级中合适的挂载位置 |
| 3 | create_object('Explosion_SFX', 'Sound SFX', parent_path='...Default Work Unit') | 创建音效对象 |
| 4 | create_event('Play_Explosion', 'Play', target_path='...Explosion_SFX') | 创建触发 Event |
| 5 | set_rtpc_binding('...Explosion_SFX', 'Volume', '...Distance', 'Linear') | 绑定 RTPC |
| 6 | verify_structure('...Explosion_SFX') | 验证 Event→Sound 关联和 RTPC 绑定完整性 |
| 7 | verify_event_completeness('Play_Explosion') | 验证 Event 在 2024.1 下可正常触发 |

整个流程 7 步工具调用，无需用户手动操作 Wwise 界面，LLM 通过 Function Calling Loop 自主完成。2024.1 的 Live Editing 特性使步骤 6/7 的验证结果可以即时反映到已连接的游戏实例。
