# Xpert Agent Middleware

最后更新日期：2026-07-16

## 目标

ModelMirror 的 Agent 中间件复用 classic workflow runner。一次实现会同时覆盖本地 Workflow、已发布 Xpert、Goal、HandoffExecutor 和受策略约束的 Xpert App，不创建第二套 Agent 执行器。

本轮提供四项真实能力：上下文压缩、结构化输出、持久 Todo 规划和 LLM 工具选择。Xpert 源码仅用于领域模型与交互参考，当前实现为 React/FastAPI 原生重写。

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

## API

Todo 管理接口：

- `GET /api/runtime/todos?scope_type=&scope_id=&status=`
- `POST /api/runtime/todos`
- `PATCH /api/runtime/todos/{todo_id}`
- `DELETE /api/runtime/todos/{todo_id}`

中间件菜单仍由 `GET /api/runtime/middleware-nodes` 提供元数据和配置 schema。执行支持仍由 workflow validate 与 classic runner 决定。

## 安全与观测

- RunRegistry checkpoint 只保存中间件名、状态、耗时、数量和错误摘要。
- 不记录 prompt、上下文正文、Todo 正文、工具输出、schema 修复输入或密钥。
- 工具选择器不能恢复被 policy 拒绝的工具。
- 中间件异常不能绕过节点的 retry、fallback 或 `exceptionHandling`。
- 公共 App 的 Todo 不持久化；其上下文摘要也不写入 Xpert 私有会话。

## 后续阶段

1. `XPERT-MIDDLEWARE-HITL-02`：工具审批、人工确认、暂停恢复、超时与升级。
2. `XPERT-MIDDLEWARE-SANDBOX-03`：沙箱文件、命令执行、Skill、浏览器和客户端工具。
3. `XPERT-MIDDLEWARE-AUTOMATION-04`：定时任务、Ralph Loop、知识写入器和插件 Hook。
4. `XPERT-MIDDLEWARE-CONSOLIDATION-05`：补齐剩余能力并统一发布预检和测试矩阵。

HITL、浏览器、沙箱、自动化和 Workflow Engine V2 不属于本轮范围。
