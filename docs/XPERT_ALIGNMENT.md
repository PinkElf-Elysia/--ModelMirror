# Xpert 对齐总纲

最后更新日期：2026-07-09
维护人：模镜团队

## 2026-07-09 增量：XPERT-WORKSPACE-HUB-02

`/studio` 已从只读资源总览推进到 Xpert 式工作空间资源 Hub 第二版：顶部新增“快速创建 / 连接”入口，覆盖创建工作流、生成工作流草稿、管理知识库、连接 MCP、安装 Skill 和查看 Runtime 运维；资源卡片补充主操作、次操作、标签与计划状态；搜索、分类和标签过滤可以同时生效；`API 工具` 与 `数据库` 作为待接入资源卡片展示，不会跳转到不存在页面。运行摘要基于现有 `/api/runtime/runs?limit=8` 做轻量统计，并继续指向 `/runtime` 查看详情。

本轮仍是前端只读聚合视图，不新增后端聚合 API，不引入 Workspace 权限、持久化资源表或资源创建编排。任一资源 API 失败时只影响对应卡片，工作空间页面整体保持可打开。

## 对齐原则

模镜接下来以 `C:\Users\21547\Downloads\xpert-main\xpert-main` 和真实 Xpert 前端界面作为主要参考源，采用“领域模型对齐 + 原生实现改写”的策略推进。项目继续保留现有 React、FastAPI、Pydantic、pytest 架构，不迁移 Xpert 的 Nx、NestJS、Angular 主框架，也不整文件复制上游源码。

EvoAgentX 只保留为历史参考：此前元智能体曾借鉴其 `goal -> sub_tasks -> inferred edges` 的规划形态，但后续近期功能规划不再以 EvoAgentX 为来源。未对齐的 EvoAgentX 能力会在 Xpert 架构主线稳定后再评估。

## 对齐主线

长期主线按产品骨架排序，而不是按单个节点或单个 API 随机扩展：

1. 工作空间资源：统一呈现智能体、知识库、MCP 工具集、API 工具、Skill、提示词、环境、运行记录。
2. Xpert Studio 画布：对齐智能体画布、节点库、右侧配置面板、预览/发布/运行入口。
3. Agent / Handoff / RunRegistry：建立任务、移交、运行记录、checkpoint、人工处理与未来调度的稳定底座。
4. Toolset / MCP / Plugin / Skill：统一工具来源、工具权限、工具审计、插件市场和技能库。
5. Knowledge Pipeline：把现有 RAG 逐步拆成 FileAsset、Artifact、Chunk、CitationAnchor、流水线草稿与执行观测。
6. Environment / Sandbox / Memory / Observability：补齐环境变量、受限执行、文件工作区、记忆写入、日志与监测面板。

## 能力矩阵

| 能力域 | 当前状态 | 已完成 | 当前边界 | 下一步 |
| --- | --- | --- | --- | --- |
| 工作空间资源 | 部分实现 | `/studio` 已作为 Xpert 式资源 Hub，聚合智能体、工作流、知识库、MCP、API 工具、数据库、Skill、提示词、环境、运行记录，并支持快速入口、标签过滤和运行摘要 | 当前是前端只读聚合视图，不做 workspace 权限、持久化资源表或资源创建编排；API 工具与数据库仍为待接入卡片 | `XPERT-WORKFLOW-REGISTRY-API-01` |
| Xpert Studio 画布 | 部分实现 | classic `/workflow`、节点库浮层、配置/运行 tabs、前端节点 registry、Xpert 分类节点菜单、智能体配置侧栏分区、多个 Xpert 对齐节点 | 仍是 classic workflow 画布，不是完整 Xpert Studio；高级配置先保存为草稿，不改变执行语义 | 后续逐步接入配置真实语义 |
| Runtime Middleware | 部分实现 | middleware lifecycle、`event_recorder`、`system_prompt_injector`、`tool_policy`、`tool_audit` | 仍以内存态为主，部分 middleware 仅最小执行 | 继续挂到 Agent/Workflow 节点运行链 |
| Agent Task | 部分实现 | AgentTask API、MetaAgent 任务工作台、workflow `agent_task` 节点 | 不做真实多 Agent 调度或持久化队列 | 与 Handoff/RunRegistry 继续闭环 |
| Handoff | 部分实现 | Handoff API、workflow `agent_handoff`、`handoff_router`、MetaAgent Inbox 手动处理 | pending/accepted/completed 仍是人工内存态流程 | 后续做队列、死信、目标 Agent 执行 |
| RunRegistry / Trace | 部分实现 | workflow/chat/agent_task/agent_handoff run，checkpoint，workflow/chat 观测与 `/runtime` 运维总览 | 内存态，可观测索引，不是调度器；`/runtime` 只做只读聚合 | 失败摘要、重试入口、持久化评估 |
| Workflow Agent | 部分实现 | `workflow_agent` 节点，模型执行，Runtime Toolset 工具模式，Xpert 式配置侧栏分区 | 轻量 JSON 决策，不是 function calling；重试、备用模型、记忆写入等配置暂只保存草稿 | 后续逐项接入真实运行语义 |
| Chat Toolset | 部分实现 | `/api/chat` 可选 MCP 工具模式，chat run 与 checkpoint | 默认关闭，不改变普通聊天；无自动 handoff | 补工具偏好、安全提示和观测 UI |
| Toolset / MCP | 部分实现 | `MCPToolsetProvider`、`run_tool_with_runtime`、tool policy/audit、MCP 管理基础、`/runtime` MCP Runtime 只读运维，`/studio` 已提供 MCP 与 Runtime 入口 | 缺 Xpert 式 Toolset 资源模型；Runtime Ops 先聚合现有 session/tool 元信息 | `XPERT-RUNTIME-OPS-02` |
| Plugin / Skill | 部分实现 | `/skills` 与 Skill 安装基础，Docker 已补 git/npm/npx 依赖，`/runtime` 可查看已安装 Skill 摘要 | 尚未形成 Xpert 插件市场/Skill 工作区统一模型；运维页不执行安装/卸载 | 先补市场与安装状态，再抽象资源模型 |
| Knowledge Pipeline | 部分实现 | RAG pipeline 只读元数据 API、Xpert 式四段 stage 草稿视图、`knowledge_citation` 工作流节点 | 不改上传、切分、向量库和聊天 RAG 主路径；图像理解 stage 仅为规划占位 | `XPERT-RUNTIME-OPS-01` |
| Prompt / Slash Command | 下一步 | 仅有提示词资源页雏形和聊天 prompt 使用 | 尚无 Xpert 式工作区提示词/命令配置 | 放在工作空间资源后推进 |
| Environment / Sandbox | 暂缓 | Docker/MCP/Skill 运行依赖逐步补齐 | 尚无 Xpert 环境变量、沙箱实例、文件工作区语义 | 等 Workspace Hub 和 Runtime Ops 稳定后推进 |
| Memory / Logs / Monitor | 暂缓 | RunRegistry events/checkpoints/audit 摘要 | 尚无完整记忆写入、日志和监测页面 | 等 Agent 配置侧栏与运行观测稳定后推进 |

## 已实现基线

- `/api/chat` 默认保持普通 SSE 聊天；显式启用 `tool_mode=mcp_tools` 时进入 Runtime Toolset 工具循环，登记 chat run、checkpoint、tool events 与审计摘要。
- Classic workflow 已支持 `workflow_agent`、`agent_task`、`agent_handoff`、`handoff_router`、`knowledge_citation`、`mcp_tool`、`runtime_middleware` 等 Xpert 对齐节点。
- `/workflow` 节点库已从平铺数组收敛为前端 `workflowNodeRegistry`，按工作流、中间件、知识流水线 tab 和逻辑、转换、工具、记忆、其他等 Xpert 分类渲染；拖拽协议和运行语义不变。
- `/workflow` 中 `agent` 与 `workflow_agent` 的右侧配置已对齐为 Xpert 式分区侧栏，包含节点、参数、提示词/模型、中间件、知识库、工具、运行策略、输出结构和记忆写入；其中高级区块当前只保存配置草稿。
- `MCPToolsetProvider`、`CapabilityRegistry`、`run_tool_with_runtime` 已成为 MCP 工具调用主路径。
- `ToolPermissionPolicy` 与 `InMemoryToolAuditStore` 已对 workflow/chat 工具调用提供最小权限与审计。
- `/runtime` 已作为 Xpert Runtime Ops 第一版，只读聚合 MCP sessions、Tool Registry、RunRegistry checkpoints 与 Skill 安装摘要。
- AgentTask/Handoff API 已支持创建、查询、accept、reject、complete；MetaAgent 页面可查看任务和 Handoff Inbox。
- RunRegistry 已支持 workflow、workflow_agent、agent_task、agent_handoff、chat 等 run 类型，并提供 checkpoint 查询。
- 本地 RAG 之上已有 Knowledge Pipeline 只读元数据视图：FileAsset、Artifact、KnowledgeChunk、CitationAnchor，并已派生数据源、处理器、分块器、图像理解四段 stage 草稿。
- `/studio` 已成为 Xpert 对齐工作空间入口，前端以软降级方式读取现有 RAG、MCP、Skill 与 RunRegistry API，展示资源卡片、分类筛选、搜索和最近运行摘要。

## Xpert UI 证据摘要

详见 `docs/XPERT_UI_REFERENCE.md`。本轮截图与源码侦察确认 Xpert 的产品骨架主要包括：

- Xpert Studio：左侧工作区导航、中心画布、右侧节点配置、顶部预览/发布/功能入口。
- 节点库菜单：工作流、中间件、知识流水线、工具集分别有清晰分类。
- 智能体配置侧栏：参数、中间件、知识库、工具、失败重试、备用模型、异常处理、输出结构、记忆写入。
- 工作空间资源：数字专家、内置工具、MCP 工具集、API 工具、知识库、数据库、Skill、提示词、环境。
- 运维与市场：MCP Runtime 运维、插件市场、技能市场、提示词工作流、环境变量面板。

## 分阶段路线

### 阶段 1：资源与导航归拢

目标：先让用户能从一个 Xpert 式工作空间入口理解系统中有哪些资源，而不是继续在分散页面之间跳转。

- `XPERT-WORKSPACE-HUB-01`：已完成第一版工作空间资源总览，聚合智能体、知识库、MCP、Skill、提示词、环境、Run 入口。
- 当前边界：只读聚合、软降级、不破坏现有入口；暂不引入 workspace 权限、资源创建编排或后端聚合 API。

### 阶段 2：画布节点体系收敛

目标：把 classic workflow 节点从散落的静态列表收敛为 Xpert 分类节点注册表。

- `XPERT-WORKFLOW-PALETTE-01`：已完成第一版前端节点 registry，按逻辑、转换、工具、记忆、其他、中间件、知识流水线分类渲染节点库。
- 当前边界：registry 先放前端本地；未实现的数据库、注释、知识流水线 stage 只显示禁用占位，不生成节点；拖拽 payload、validate、runner 和 SSE 协议保持不变。

### 阶段 3：智能体配置面板对齐

目标：把当前节点配置表单升级为 Xpert 式智能体配置侧栏，但不一次性实现全部高级语义。

- `XPERT-STUDIO-PANEL-01`：已完成第一版 `agent` / `workflow_agent` 配置侧栏分区，补齐参数、中间件、知识库、工具、失败重试、备用模型、异常处理、输出结构、记忆写入等 UI 区块。
- 当前边界：除已有模型调用与工具模式外，新区块只保存配置草稿；执行语义按后续小步接入。

### 阶段 4：知识流水线从只读到草稿

目标：从当前 RAG 元数据视图推进到可视化知识流水线草稿。

- `XPERT-KNOWLEDGE-PIPELINE-02`：已引入数据源、处理器、分块器、图像理解四类 stage 的只读草稿 API 与 `/rag` UI。
- 当前边界：不迁移向量库，不改变 `/api/rag/query`，不执行真实图像理解；只新增可观测草稿层。

### 阶段 5：运行与工具运维收口

目标：补齐 Xpert 的运行、插件、工具、环境和观测管理体验。

- `XPERT-RUNTIME-OPS-01`：已完成 `/runtime` 第一版运维入口，聚合 MCP Runtime、Tool Registry、RunRegistry 与 Skill Runtime 摘要。
- 当前边界：只读观测，不替代 `/mcps` 或 `/skills` 的管理操作；不新增后端协议、不展示密钥、完整 prompt 或工具输出。

## 近期 5 步工程顺序

1. `XPERT-WORKFLOW-REGISTRY-API-01`：评估是否把前端节点 registry 升级为后端统一 registry API，避免未来前后端元数据漂移。
2. `XPERT-STUDIO-PANEL-02`：逐项接入重试、备用模型、输出结构、记忆写入等真实执行语义。
3. `XPERT-RUNTIME-OPS-02`：在 `/runtime` 上补失败摘要、重试入口占位、MCP runtime 状态细分和环境观测。
4. `XPERT-KNOWLEDGE-PIPELINE-03`：在 stage 草稿稳定后评估可编辑流水线草稿和执行观测，不迁移现有 RAG 主路径。
5. `XPERT-WORKSPACE-RESOURCE-MODEL-01`：当 Hub 入口稳定后，再评估是否抽象 workspace 资源模型与后端聚合 API。

## 验收护栏

每个后续对齐任务至少包含：

- 后端语法检查：`python -m py_compile server/main.py server/xpert_runtime/*.py server/workflow_native/*.py`
- 相关 pytest：按模块新增或更新 `server/tests/test_xpert_runtime_*.py`、workflow 节点测试或 RAG 测试。
- 前端构建：涉及前端时运行 `cd client && npm.cmd run build`。
- Docker smoke：影响主路径时运行 `docker compose -p modelmirror up -d --build --force-recreate` 与 `/api/health`。
- 文档更新：同步更新本总纲或相关模块文档，说明状态、边界和下一步。
- 安全检查：不得提交 `.env`、真实 API key、完整工具输出、完整 prompt、embedding、本地绝对文件路径或密钥。

## 开源与参考边界

- Xpert：只参考领域模型、交互结构、文案分类、运行时分层和测试思路；默认参考改写，不复制源码。
- EvoAgentX：只保留历史归因说明，不继续扩展其 runtime、optimizer、RAG、MCP toolkit 或 dependency graph。
- 第三方仓库：可用于确认公开能力边界和术语，但不得直接搬运实现；如必须引用片段，先确认许可证兼容并在文档记录来源。
