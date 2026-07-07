# Xpert 对齐总纲

> 2026-07-06 状态补充：Workflow Agent 节点已进入“部分实现”。Classic workflow 现在可拖入 `workflow_agent` 节点，用角色提示词和任务输入调用模型，输出结果到变量，并登记 `workflow_agent` 子 run。当前仍是单步模型执行，不接工具调用、Handoff 自动调度或真实多 Agent 协作。

> 2026-07-06 状态补充：Handoff Queue 已进入“部分实现”。Handoff metadata 现在记录 accepted/rejected/completed 的处理者、时间和结果/原因；MetaAgent Handoff Inbox 支持按状态和目标 Agent 筛选，并可填写完成结果。当前仍是内存态人工处理闭环，不做真实调度、worker 队列或持久化。

> 2026-07-06 状态补充：Handoff 前端观测已进入“部分实现”。Workflow 运行观测可以按 `parent_run_id` 拉取 `agent_task` / `agent_handoff` 子 run；MetaAgent 任务工作台可以查看任务 handoff 记录，并通过 Handoff Inbox Beta 手动 accept / reject / complete。当前仍不做真实多 Agent 调度、队列分派、数据库持久化或目标 Agent 自动执行。

> 2026-07-05 状态补充：RunRegistry 已进入最小可观测闭环阶段，详见文末“RunRegistry 最小可观测闭环”。

## 2026-07-05 增量：RunRegistry 最小可观测闭环

RunRegistry 已从“下一步”进入“部分实现”。当前新增 `server/xpert_runtime/run_registry.py`，提供内存态 `RuntimeRun` 与 `RunRegistry`，统一登记 `workflow`、`workflow_agent`、`agent_task`、`agent_handoff` 四类 run，支持创建、查询、过滤列表、状态更新和取消。

Classic workflow 运行时会创建 workflow run，并在 `workflow_meta` / `workflow_end` SSE 中携带 `run_id`；`workflow_agent` 节点执行模型智能体步骤时登记 workflow_agent run；`agent_task` 节点创建任务时登记 agent_task run；`agent_handoff` 节点创建移交时登记 agent_handoff run。Run 之间通过 `parent_run_id` 和 metadata 关联，不强行合并现有 workflow `task_id`，避免破坏既有 SSE、status 和 resume 协议。

新增 API：

- `GET /api/runtime/runs?run_type=&status=&limit=`
- `GET /api/runtime/runs/{run_id}`
- `POST /api/runtime/runs/{run_id}/cancel`

当前边界：RunRegistry 仅为内存态可观测索引，不是持久化调度器；取消 run 只更新 registry 状态，不中断真实 workflow、AgentTask 或 Handoff 执行。下一步可在此基础上继续补齐 Handoff 前端观测、RunRegistry 页面、checkpoint、死信与持久化存储。

最后更新日期：2026-07-06
维护人：模镜团队

## 对齐原则

模镜接下来以 `C:\Users\21547\Downloads\xpert-main\xpert-main` 为主要参考源，采用“原生移植 + 参考改写”的策略对齐 Xpert 的能力边界。项目继续保留现有 React、FastAPI、Pydantic、pytest 架构，不迁移 Xpert 的 Nx、NestJS、Angular 主框架，也不整文件复制上游源码。

EvoAgentX 只保留为历史参考：此前元智能体曾借鉴其 `goal -> sub_tasks -> inferred edges` 的规划形态，但后续不再以 EvoAgentX 作为近期功能规划来源。未对齐的 EvoAgentX 能力会在 Xpert 架构主线稳定后再评估是否补齐。

## 长期能力目标

| 能力域 | Xpert 对齐目标 | 当前状态 | 下一步 |
| --- | --- | --- | --- |
| Runtime / Execution | 中间件生命周期、任务注册、事件记录、运行观测 | 部分实现 | 建立 Handoff / RunRegistry 闭环 |
| Agent / Handoff | AgentTask、任务移交、子 Agent、主管-专家协作 | 部分实现 | 将 workflow_agent 接入工具与 Handoff 编排 |
| Workflow | Xpert 节点类型、Agent 节点、工具节点、知识流水线节点 | 部分实现 | 扩展 workflow_agent toolset、subflow、知识类节点 |
| Toolset / MCP | 统一 Toolset Provider、权限、审计、偏好 | 部分实现 | 将聊天 Agent 和工作流 Agent 统一接入 toolset capability |
| Knowledge Pipeline | FileAsset、Artifact、Chunk、CitationAnchor、Embedding | 待实现 | 从本地 RAG 元数据模型开始拆分 |
| Claw / Skill | 用户偏好、工作区 Skill、会话临时选择 | 待实现 | 在 Xpert workspace / skill 抽象稳定后接入 |
| Environment / Sandbox | 工作区文件、受限执行、浏览器/终端能力 | 待实现 | 先做受限文件 API 和 workspace volume |
| Observability | trace、checkpoint、usage、事件查询面板 | 部分实现 | 运行观测从工具事件扩展到 Agent/Handoff |

## 当前已落地能力

- Runtime Middleware：已具备 `before_agent`、`before_model`、`wrap_model_call`、`after_model`、`after_agent`、`wrap_tool_call` 生命周期。
- Chat Runtime：`/api/chat` 已接入默认 runtime pipeline，支持 system prompt 注入和模型调用事件记录。
- Toolset / MCP：`mcp_tool` 已通过 `MCPToolsetProvider`、`CapabilityRegistry`、`run_tool_with_runtime` 调用工具。
- Tool Policy / Audit：`tool_policy` 可影响 workflow 内 MCP 工具调用，`InMemoryToolAuditStore` 提供最小审计记录。
- Runtime Middleware Node：前端可拖入 `runtime_middleware` 节点，`system_prompt_injector`、`tool_policy`、`event_recorder`、`tool_audit` 已逐步进入真实执行或可见状态。
- Workflow Agent Node：classic workflow 可拖入 `workflow_agent` 节点，使用 `rolePrompt` 作为该节点 system prompt、`taskInput` 作为用户输入调用模型，结果写入 `outputVariable`，并登记 `workflow_agent` 子 run。
- Agent Task Runtime：已提供 `AgentTaskStore`、最小 AgentTask API、MetaAgent 任务工作台，以及 classic workflow `agent_task` 节点；该节点当前负责创建任务并输出 `task_id`，暂不做真实多 Agent 调度。
- Handoff API：已提供 handoff 创建、按任务查询、接受、拒绝、完成的内存态 API，状态转移限定为 `pending -> accepted/rejected`、`accepted -> completed`，并写入 `agent.handoff.created/accepted/rejected/completed` runtime events。
- 运行观测：classic workflow 可查询 per-task runtime events 和 tool audit records，前端 `WorkflowRun` 已提供“运行观测”折叠区。

## 近期交付顺序

1. **Workflow Agent Toolset**：让 `workflow_agent` 可选择 MCP Toolset，复用 tool policy / audit。
2. **RunRegistry Trace 增强**：补齐 workflow_agent / handoff 的 trace、checkpoint、失败摘要与重试入口。
3. **Handoff 自动编排雏形**：将 workflow_agent 输出与 handoff queue 连接，但仍保持人工可控。
4. **知识流水线底座**：拆分本地 RAG 的文件元数据，建立 FileAsset -> Artifact -> Chunk -> CitationAnchor 的最小模型。

## 源码与协议策略

- Xpert：仅参考协议、领域模型、运行时分层和测试思路；默认参考改写，不整文件复制。
- EvoAgentX：保留历史归因说明，不继续扩展其 runtime、optimizer、RAG、MCP toolkit 或 dependency graph。
- 第三方协议：任何复制片段前必须确认许可证兼容，并在文档中记录来源；默认不复制源码。

## 验收护栏

每个后续对齐任务至少包含：

- 后端语法检查：`python -m py_compile server/main.py server/xpert_runtime/*.py`
- 相关 pytest：按模块新增 `server/tests/test_xpert_runtime_*.py` 或 workflow 节点测试。
- 前端构建：涉及前端时运行 `cd client && npm.cmd run build`。
- Docker smoke：影响主路径时运行 `docker compose -p modelmirror up -d --build --force-recreate` 和 `/api/health`。
- 文档更新：同步更新本文件或相关模块文档，说明状态、边界和下一步。
