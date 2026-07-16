# Xpert Agent Middleware

最后更新日期：2026-07-16

## 目标

ModelMirror 的 Agent 中间件复用 classic workflow runner。一次实现会同时覆盖本地 Workflow、已发布 Xpert、Goal、HandoffExecutor 和受策略约束的 Xpert App，不创建第二套 Agent 执行器。

当前提供五项真实能力：上下文压缩、结构化输出、持久 Todo 规划、LLM 工具选择和可恢复的人机审批。Xpert 源码仅用于领域模型与交互参考，当前实现为 React/FastAPI 原生重写。

## 绑定模型

`runtime_middleware` 通过 `sourceHandle="middleware-binding" -> targetHandle="middleware"` 的边绑定到一个 `workflow_agent`。绑定边具有以下约束：

- 绑定节点不参与控制流拓扑、变量可达性、节点调度或独立执行。
- 一个中间件节点只能绑定一个 `workflow_agent`。
- 同一个中间件节点不能同时拥有绑定边和普通控制流边。
- 同一 Agent 的中间件按 `middlewarePriority` 升序、节点 ID 次序稳定编译。
- 普通边连接的旧中间件仍保持线性语义，并影响其后执行的 Agent。

每个 `workflow_agent` 会编译独立 `MiddlewarePipeline`。Agent 生命周期执行 `before_agent/after_agent`，直接模型调用和 ReAct 决策调用执行 `before_model/after_model`，工具继续经过相同 pipeline、tool policy 和 audit。

## 核心中间件

### Context Compression

`context_compression` 使用无 tokenizer 的保守 token 估算，在达到上下文预算触发比例时总结旧消息，并保留最近消息。Xpert Chat 的派生摘要写入 `XpertContextStore`，包含 revision、摘要模型和覆盖到的 message ID；原始消息不修改。

摘要失败时保留最近上下文并产生 warning。普通 Workflow、Goal 和 Handoff 使用运行态摘要；公共 App 只使用本次调用的临时摘要。

### Structured Output

`structured_output` 使用 Draft 2020-12 JSON Schema 校验 Agent 最终答案，不校验 ReAct 工具决策。第一次不合法时允许用当前执行模型修复一次；仍不合法时进入节点已有 retry、fallback 和 `exceptionHandling`。

成功结果会以规范 JSON 文本替换原答案，SSE 事件类型保持不变。现有 `outputSchemaMode/outputSchemaJson` 会编译为隐式结构化中间件，显式绑定配置优先。

### Todo Planner

`todo_planner` 提供 `todo_list`、`todo_create`、`todo_update` Runtime 工具，并继续经过 policy、audit 和 middleware。Todo 使用 revision 防止覆盖、遵守中间件配置的单作用域数量上限，并通过 `RuntimeTodoStore` 原子保存。

作用域：

- Xpert Chat：`conversation`
- Goal：`goal + step`
- Handoff：`handoff`
- 普通 Workflow：`task + node`
- Xpert App：`app_run`，只在本次进程运行内存在，不跨公共调用者持久化

Todo 是执行辅助状态，不替代 GoalStep，也不修改 GoalCoordinator 的依赖图。

### LLM Tool Selector

`llm_tool_selector` 在 Agent allowlist 和 tool policy 过滤之后运行。模型只能从已配置、已授权的工具中选择；Todo 等中间件必需工具强制保留。非法 JSON、超时或模型失败时使用确定性关键词排序回退。

选择结果只作用于当前 Agent run，不修改 Tool Registry、MCP session 或已发布 XpertVersion。

### Human In The Loop

`human_in_the_loop` 可以审批匹配的工具调用，也可以在最终答案写入变量前要求确认。工具审批顺序固定为 allowlist / tool policy、HITL、audit started、Provider、audit finished/failed；被 policy 拒绝的工具不会产生可绕过权限的审批入口。

- `interrupt_on_tools` 接受逗号或换行分隔工具名，`*` 表示审批所有工具。
- 工具决策支持批准、编辑参数和拒绝。编辑不能更换工具名，并会重新执行 schema 与运行时权限校验。
- 拒绝不会调用 Provider，人工原因作为合成工具结果返回 ReAct 循环，模型可以选择其他方案。
- `final_confirmation` 支持批准、人工替换或带反馈修订。修订轮数受 `max_revision_rounds` 限制。
- 审批超时范围为 30 秒至 24 小时，默认 1 小时；超时永不自动批准。

暂停由 `RuntimeApprovalStore` 和 `WorkflowExecutionStore` 原子持久化。执行状态保存队列、变量、已执行节点和当前 Agent 的 ReAct 轮次；审批决定后由单进程 `ApprovalCoordinator` 使用 lease 恢复。已完成节点不会重跑，待审批工具最多执行一次。服务重启会清除旧 lease 并恢复等待中的 execution。

Workflow 与 Xpert Chat 可重新连接 `GET /api/workflow/run/{task_id}/stream?after_sequence=` 读取安全事件日志。GoalStep、AgentTask 和 Handoff 在等待时使用 `waiting_approval`；审批过期后进入 `needs_attention`，不计入模型或工具重试。旧 `human_intervention` 节点继续保留既有 SSE 与 `/resume` API，但底层改用同一持久暂停存储。

## API

Todo 管理接口：

- `GET /api/runtime/todos?scope_type=&scope_id=&status=`
- `POST /api/runtime/todos`
- `PATCH /api/runtime/todos/{todo_id}`
- `DELETE /api/runtime/todos/{todo_id}`

审批与恢复接口：

- `GET /api/runtime/approvals?status=&task_id=&run_id=&scope_type=&scope_id=&limit=`
- `GET /api/runtime/approvals/{approval_id}`
- `POST /api/runtime/approvals/{approval_id}/decide`
- `POST /api/runtime/approvals/{approval_id}/reopen`
- `POST /api/runtime/approvals/{approval_id}/cancel`
- `GET /api/runtime/approval-coordinator/status`
- `GET /api/workflow/run/{task_id}/stream?after_sequence=`

审批决定必须携带当前 `revision`。重复或过期决定返回冲突，不会重复恢复执行。新增兼容 SSE 事件为 `runtime_approval_pending` 和 `runtime_approval_resolved`。

中间件菜单仍由 `GET /api/runtime/middleware-nodes` 提供元数据和配置 schema。执行支持仍由 workflow validate 与 classic runner 决定。

## 安全与观测

- RunRegistry checkpoint 只保存中间件名、状态、耗时、数量和错误摘要。
- 不记录 prompt、上下文正文、Todo 正文、工具输出、schema 修复输入或密钥。
- 工具选择器不能恢复被 policy 拒绝的工具。
- 中间件异常不能绕过节点的 retry、fallback 或 `exceptionHandling`。
- 公共 App 的 Todo 不持久化；其上下文摘要也不写入 Xpert 私有会话。
- 公开 Xpert App 与 OpenAI 兼容 API 禁止部署 `human_in_the_loop` 或 `human_intervention`，避免无客户端连接时悬挂请求。
- 审批列表、事件和 checkpoint 只保存脱敏参数、ID、状态和错误摘要；完整 prompt、工具结果与密钥不得进入公共接口。
- `RuntimeInterrupt` 与审批存储错误属于不可 fail-open 中断，工具 runner 不得降级为直接调用 Provider。

## 后续阶段

1. `XPERT-MIDDLEWARE-SANDBOX-03`：沙箱文件、命令执行、Skill、浏览器和客户端工具。
2. `XPERT-MIDDLEWARE-AUTOMATION-04`：定时任务、Ralph Loop、知识写入器和插件 Hook。
3. `XPERT-MIDDLEWARE-CONSOLIDATION-05`：补齐剩余能力并统一发布预检和测试矩阵。

浏览器、沙箱、自动化和 Workflow Engine V2 仍不属于当前范围。
