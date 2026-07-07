# workflow-native 自研工作流设计

> 2026-07-06 状态补充：classic workflow 新增 `workflow_agent` 节点。该节点使用 `rolePrompt` 作为该节点 system prompt、`taskInput` 作为用户输入调用模型，流式输出结果并写入 `outputVariable`，同时登记 `workflow_agent` 子 run。当前是单步模型智能体执行，不接 MCP 工具、Handoff 自动调度或真实多 Agent 协作。

> 2026-07-06 状态补充：Handoff Queue 进入人工处理闭环。`accept/reject/complete` 会记录处理者、处理时间和结果/原因摘要，并同步到 `agent_handoff` run metadata；`WorkflowRun` 子 run 摘要会展示 handler/result。当前不做自动调度、目标 Agent 执行、持久化队列或权限系统。

> 2026-07-06 状态补充：Handoff 观测前端进入最小闭环。`GET /api/runtime/runs` 支持按 `parent_run_id` / `source_id` 查询，`WorkflowRun` 的“运行观测”可展示 workflow 下的 `agent_task` 与 `agent_handoff` 子 run；新增 `GET /api/runtime/agent-handoffs?task_id=&status=&target_agent=&limit=` 供 MetaAgent Handoff Inbox 查询。当前只做观测和手动状态操作，不做真实调度、队列或持久化。

> 2026-07-05 状态补充：classic workflow 已接入 RunRegistry 最小可观测闭环，并恢复 `/workflow` 画布的节点库浮层与配置/运行 tabs 布局。

## 2026-07-05 增量：RunRegistry 与工作流运行观测

Classic workflow 每次运行会登记一条 `workflow` run，并在 `workflow_meta` / `workflow_end` SSE 中携带 `run_id`。`workflow_agent` 节点执行模型智能体步骤时同步登记 `workflow_agent` run；`agent_task` 节点创建 AgentTask 时同步登记 `agent_task` run；`agent_handoff` 节点创建 Handoff 时同步登记 `agent_handoff` run。四类 run 通过 `parent_run_id` 与 metadata 互相关联，保留现有 workflow `task_id`、AgentTask `task_id` 与 Handoff `handoff_id` 协议不变。

新增 Runtime Run API 用于最小观测：

- `GET /api/runtime/runs?run_type=&status=&limit=`
- `GET /api/runtime/runs/{run_id}`
- `POST /api/runtime/runs/{run_id}/cancel`

当前 RunRegistry 是内存态索引，不是调度器；取消 run 仅更新观测状态，不中断正在执行的 workflow、AgentTask 或 Handoff。前端 `WorkflowRun` 的“运行观测”折叠区会展示当前 `run_id` 与 RunRegistry 摘要，并继续展示 runtime events 与 tool audit records。

## 2026-07-05 增量：`/workflow` 画布布局恢复

`/workflow` 布局恢复为“画布 + 单一右侧工作台”：节点库位于画布顶部附近的下拉/浮层中，避免常驻左栏；右侧工作台使用 `配置 / 运行` tabs 承载 `NodeConfig` 与 `WorkflowRun`，点击运行时切到运行页。该调整只恢复布局体验，不改变节点数据结构、拖拽 payload、SSE 协议或后端执行逻辑。

workflow-native 是模镜自研工作流引擎的渐进式实验线。它不会替换当前稳定的 `/workflow` Dify iframe 入口，也不会改动 `/rag`。当前阶段提供静态图校验能力，并在 classic 运行器中试点少量本地节点执行，让团队先把数据模型、API 契约、错误模型和测试流程立起来。

最后更新日期：2026-07-06
维护人：模镜团队

## 目标与边界

目标：

- 在独立路由 `/workflow-native` 中承载自研实验，不影响 `/workflow`。
- 复用 classic 画布的 `WorkflowDefinition` 结构，避免前后端出现两套图模型。
- 提供 `/api/workflow-native/validate`，只做静态校验，不执行节点。
- 在 `/api/workflow/run` classic 运行器中试点 `variable_assign`、`http_request`、`list_operation`、`iteration` 四类本地节点。
- 为后续 `/api/workflow-native/run`、模板、版本迁移和 Dify 导入打接口基础。

本阶段不做：

- workflow-native API 自身不执行 LLM、Tool、MCP、RAG 或代码节点。
- 不实现跨节点子图循环，`iteration` 当前只在单节点内对逗号分隔文本做本地迭代。
- 不替换 Dify iframe。
- 不实现发布、版本管理、观测面板、并行 DAG 或循环。
- 不迁移 `/workflow/classic` 的运行行为。

## 与 Dify 并行策略

稳定路径继续由 Dify 提供：

```text
/workflow        -> Dify iframe 稳定工作流
/rag             -> Dify 或本地 RAG 稳定入口
/workflow/classic -> 早期 React Flow MVP 画布
/workflow-native -> 自研工作流实验线
```

如果 native 实验出现问题，回滚方式是关闭或隐藏 `/workflow-native` 路由和 Studio 卡片；`/workflow` 和 `/rag` 不需要改动。

## 图模型

前端类型：

```typescript
interface NativeWorkflowDefinition extends WorkflowDefinition {
  version: string;
  source: "workflow-native" | "classic" | "dify-import";
}
```

后端模型位于 `server/workflow_native/schemas.py`，字段对齐 classic 的 `WorkflowPayload`：

```json
{
  "id": "draft",
  "title": "linear",
  "version": "native-draft",
  "source": "workflow-native",
  "nodes": [
    {
      "id": "input",
      "type": "input",
      "data": {
        "kind": "input",
        "variableName": "user_input"
      }
    }
  ],
  "edges": [
    {
      "id": "e1",
      "source": "input",
      "target": "llm"
    }
  ]
}
```

## Dify 概念映射

| Native 节点 | Dify 概念 | 当前差异 |
| --- | --- | --- |
| `input` | `start` / user input | native 只声明变量名，Dify 支持完整输入表单。 |
| `llm` | `llm` | native 当前只校验 `modelId`、`prompt`、`outputVariable`。 |
| `condition` | `if-else` | native MVP 只支持 `equals`、`contains`。 |
| `code` | `code` | native 只允许安全内置字符串操作，Dify 使用沙箱代码执行。 |
| `variable_assign` | `variable-assigner` | native 把模板渲染进一个变量，不实现 Dify 的复杂变量写入策略。 |
| `template_transform` | `template-transform` | native 当前是长文本模板渲染器，不做文件导出。 |
| `variable_aggregator` | `variable-aggregator` | native 聚合字符串变量，输出文本或 JSON 字符串。 |
| `parameter_extractor` | `parameter-extractor` | native 复用现有模型调用链，返回 JSON 字符串；无 Key 时降级为空对象。 |
| `knowledge_retrieval` | `knowledge-retrieval` | native 复用本地 RAG 服务；索引未就绪时返回 warning，不中断流程。 |
| `document_extractor` | `document-extractor` | native 仅读取受限目录内本地文件，不提供上传 UI。 |
| `question_classifier` | `question-classifier` / 问题分类器 | native 仅支持关键词规则分类，可选 LLM 回退默认关闭。 |
| `agent` | `agent` | native 提供 ReAct-Lite Agent，支持直接回答和 MCP 工具循环两种模式。 |
| `mcp_tool` | `tool` / MCP 工具 | native 调用全局 MCP 工具注册表中已连接的工具，需先在 `/mcps` 建立 Server 会话。 |
| `time_tool` | 时间工具 | native 获取当前时间、时间戳或格式化日期文本，不依赖外部服务。 |
| `http_request` | `http-request` | native 仅支持 GET/POST 文本响应，默认关闭真实出站请求。 |
| `list_operation` | `list-operator` | native 当前基于逗号分隔字符串，尚无完整数组变量系统。 |
| `iteration` | `iteration` | native 当前只做节点内迭代，不执行跨节点子图。 |
| `output` | `end` / `answer` | native 输出指定变量，Dify 支持更丰富的结束响应。 |

参考点：Dify 工作流由节点、边、变量和运行态组成；native 当前只借鉴节点概念、拓扑顺序和静态校验分类，不复制 Dify 源码实现。

暂不接入的节点：问题理解、复杂多 Agent 协作、人工介入之外的复杂审批流。这些能力依赖更完整的编排或新的异步交互模型，需要独立设计文档和测试护栏后再进入 native 实验线。

## API 契约

### GET `/api/workflow-native/templates`

返回 native 模板列表。当前只提供一个线性三节点样例。

```bash
curl http://localhost:8000/api/workflow-native/templates
```

响应：

```json
[
  {
    "id": "native-linear-starter",
    "title": "输入 -> LLM -> 输出",
    "description": "用于验证 workflow-native 静态图校验的最小三节点样例。",
    "workflow": {
      "id": "native-linear-starter",
      "title": "Native linear starter",
      "version": "native-draft",
      "source": "workflow-native",
      "nodes": [],
      "edges": []
    }
  }
]
```

### POST `/api/workflow-native/validate`

只做静态校验。即使校验失败，HTTP 仍返回 `200`，用 `valid=false` 和 `issues` 表示图本身的问题，避免和网关或服务异常混淆。

合法三节点样例：

```bash
curl -X POST http://localhost:8000/api/workflow-native/validate \
  -H "Content-Type: application/json" \
  -d "{\"workflow\":{\"id\":\"draft\",\"title\":\"linear\",\"nodes\":[{\"id\":\"input\",\"type\":\"input\",\"data\":{\"kind\":\"input\",\"variableName\":\"user_input\"}},{\"id\":\"llm\",\"type\":\"llm\",\"data\":{\"kind\":\"llm\",\"modelId\":\"openai/gpt-4o-mini\",\"prompt\":\"请回答 {{user_input}}\",\"outputVariable\":\"llm_output\"}},{\"id\":\"output\",\"type\":\"output\",\"data\":{\"kind\":\"output\",\"outputVariable\":\"llm_output\"}}],\"edges\":[{\"id\":\"e1\",\"source\":\"input\",\"target\":\"llm\"},{\"id\":\"e2\",\"source\":\"llm\",\"target\":\"output\"}]}}"
```

响应：

```json
{
  "valid": true,
  "issues": [],
  "order": ["input", "llm", "output"],
  "node_count": 3,
  "edge_count": 2
}
```

带环图样例：

```bash
curl -X POST http://localhost:8000/api/workflow-native/validate \
  -H "Content-Type: application/json" \
  -d "{\"workflow\":{\"id\":\"draft\",\"title\":\"cycle\",\"nodes\":[{\"id\":\"input\",\"type\":\"input\",\"data\":{\"kind\":\"input\",\"variableName\":\"user_input\"}},{\"id\":\"output\",\"type\":\"output\",\"data\":{\"kind\":\"output\",\"outputVariable\":\"user_input\"}}],\"edges\":[{\"id\":\"a\",\"source\":\"input\",\"target\":\"output\"},{\"id\":\"b\",\"source\":\"output\",\"target\":\"input\"}]}}"
```

响应包含：

```json
{
  "valid": false,
  "issues": [
    {
      "code": "cycle_detected",
      "message": "Workflow graph contains a cycle.",
      "severity": "error"
    }
  ],
  "order": []
}
```

### 预留 POST `/api/workflow-native/run`

该接口暂不实现。未来会按 validate 通过后的拓扑顺序执行节点，并继续保持 `/api/workflow/run` classic 行为不变。

## 错误模型

`ValidationIssue` 字段：

```json
{
  "code": "missing_input_node",
  "message": "Workflow needs at least one input/start node.",
  "severity": "error",
  "node_id": "input",
  "edge_id": "e1"
}
```

当前错误码：

- `duplicate_node_id`
- `unknown_node_kind`
- `missing_input_node`
- `missing_output_node`
- `missing_input_variable`
- `invalid_variable_name`
- `missing_llm_model`
- `missing_llm_prompt`
- `missing_llm_output_variable`
- `invalid_condition_operator`
- `missing_condition_variable`
- `missing_condition_value`
- `invalid_code_operation`
- `missing_output_variable`
- `missing_template_variable`
- `missing_condition_variable_reference`
- `missing_output_variable_reference`
- `invalid_edge_reference`
- `cycle_detected`
- `missing_variable_assign_name`
- `invalid_variable_assign_name`
- `missing_variable_assign_template`
- `missing_http_request_url`
- `invalid_http_request_method`
- `invalid_http_request_headers_json`
- `missing_http_request_output_variable`
- `invalid_http_request_output_variable`
- `missing_http_request_body_variable_reference`
- `missing_template_transform_template`
- `missing_template_transform_output_variable`
- `invalid_template_transform_output_variable`
- `missing_aggregator_variable_names_empty`
- `invalid_aggregator_variable_name`
- `missing_aggregator_output_variable`
- `invalid_aggregator_output_variable`
- `missing_aggregator_variable_reference`
- `missing_parameter_extractor_input_variable`
- `missing_parameter_extractor_schema`
- `missing_parameter_extractor_model_id`
- `missing_parameter_extractor_output_variable`
- `invalid_parameter_extractor_output_variable`
- `missing_parameter_extractor_input_variable_reference`
- `missing_knowledge_retrieval_query_variable`
- `invalid_knowledge_retrieval_top_k`
- `missing_knowledge_retrieval_output_variable`
- `invalid_knowledge_retrieval_output_variable`
- `missing_knowledge_retrieval_query_variable_reference`
- `missing_document_extractor_source_path`
- `missing_document_extractor_output_variable`
- `invalid_document_extractor_output_variable`
- `missing_document_extractor_source_path_reference`
- `missing_list_operation_input_variable`
- `invalid_list_operation_operator`
- `missing_list_operation_separator`
- `missing_list_operation_output_variable`
- `invalid_list_operation_output_variable`
- `missing_list_operation_input_variable_reference`
- `missing_iteration_input_variable`
- `missing_iteration_variable`
- `invalid_iteration_variable`
- `missing_iteration_template`
- `missing_iteration_output_variable`
- `invalid_iteration_output_variable`
- `missing_iteration_input_variable_reference`

## 测试流程

后端测试：

```bash
python -m pytest server/tests/test_workflow_native_validate.py -q
```

全量后端回归：

```bash
python -m pytest server/tests/ -q
```

前端构建：

```bash
cd client
npm.cmd run build
```

## 2026-06-17 增量：人工介入节点

`human_intervention` 已进入 workflow-native / classic 共享实验线。它对齐 Dify 的 Human-in-the-loop 概念，但保持 MVP 边界：仅支持文本输入、内存态暂停和 REST resume，不做持久化审批流、多人协作或权限系统。

### 节点映射

| Native 节点 | Dify 概念 | 当前差异 |
| --- | --- | --- |
| `human_intervention` | `human-in-the-loop` | native 运行器通过 SSE 暂停并等待 `/api/workflow/run/{task_id}/resume`，Dify 可提供更完整的人工审批和运行态管理。 |
| `question_classifier` | `question-classifier` / 问题分类器 | native 仅支持关键词规则分类文本到预设类别，可选 LLM 回退；Dify 可扩展为分类模型。 |
| `agent` | `agent` | native 当前提供 ReAct-Lite：模型用 JSON 决策直接回答或调用已注册 MCP 工具；复杂多 Agent 编排后续独立设计。 |

### 校验规则

`human_intervention` 节点必须包含：

- `prompt`：展示给用户的提示文案，支持 `{{variable}}`。
- `outputVariable`：用户输入写入的变量名，必须是合法标识符。

新增错误码：

- `missing_prompt`
- `missing_output_variable`
- `invalid_human_intervention_output_variable`

若 `prompt` 引用不存在的变量，沿用 `missing_template_variable`。

### Classic 运行器事件

`POST /api/workflow/run` 会在 SSE 第一条发送：

```json
{"event":"workflow_meta","task_id":"...","ttl_seconds":1800}
```

遇到 `human_intervention` 节点时，运行器发送：

```json
{
  "event": "human_intervention_pending",
  "task_id": "...",
  "node_id": "human",
  "node_title": "人工确认",
  "node_type": "human_intervention",
  "prompt": "请确认：...",
  "output_variable": "human_input"
}
```

在等待期间每 15 秒发送一次：

```json
{"event":"heartbeat","task_id":"...","node_id":"human","at":1780000000}
```

前端应消费 heartbeat，但默认不展示到运行日志。

### Resume API

```bash
curl -X POST http://localhost:8000/api/workflow/run/<task_id>/resume \
  -H "Content-Type: application/json" \
  -d "{\"node_id\":\"human\",\"input_text\":\"确认继续\"}"
```

成功响应：

```json
{"ok":true,"task_id":"...","node_id":"human"}
```

任务不存在或 TTL 过期时返回 `404`；当前未暂停时返回 `400`；节点不匹配时返回 `409`。

### Status API

```bash
curl http://localhost:8000/api/workflow/run/<task_id>/status
```

响应：

```json
{
  "task_id": "...",
  "paused": true,
  "paused_node_id": "human",
  "created_at": 1780000000.0,
  "ttl_seconds_left": 1790.0
}
```

### 运行态与回退

- 任务状态仅存放在后端内存中，TTL 为 30 分钟。
- 工作流结束、SSE 连接断开或 TTL 过期都会清理任务。
- 若出现问题，可从前端隐藏 `human_intervention` 调色板条目，或在后端将 `WORKFLOW_HUMAN_INTERVENTION_ENABLED` 设为 `False` 降级。

## 2026-06-17 增量：问题分类器节点

`question_classifier` 已进入 workflow-native / classic 共享实验线。它对齐 Dify 的问题分类器概念，但保持 MVP 边界：默认仅使用关键词规则，不调用模型；只有用户显式设置 `useLlmFallback=true` 时才尝试一次轻量 LLM 回退。

### 字段

- `inputVariable`：待分类文本变量名。
- `categories`：JSON 字符串，格式为 `{"类别":["关键词1","关键词2"]}`。
- `outputVariable`：分类结果写入变量名。
- `defaultCategory`：规则未命中或异常时写入的默认类别，默认 `未知`。
- `matchMode`：`contains_any` 或 `contains_all`。
- `caseSensitive`：`true` 或 `false`。
- `useLlmFallback`：`true` 或 `false`，默认 `false`。
- `modelId`：启用 LLM 回退时必填。
- `llmFallbackPrompt`：可选回退提示词，支持 `{{variable}}`。

### 安全边界

- LLM 回退默认关闭，常规分类不产生模型调用成本。
- 开启 LLM 回退但未配置 API Key 或 `modelId` 时，运行器会记录 `error` 事件并写入 `defaultCategory`，不会中断工作流。
- `categories` 只接受 JSON 对象和字符串数组，不支持正则、脚本或 DSL。

## 2026-06-17 增量：MCP 工具与时间工具节点

`mcp_tool` 与 `time_tool` 已进入 workflow-native / classic 共享实验线。

- `mcp_tool` 字段：`toolName`、`argumentsJson`、`outputVariable`。运行前需要先在 `/mcps` 连接 MCP Server，工具进入全局注册表后才能被调用。`argumentsJson` 支持 `{{variable}}` 模板，模板替换后必须仍是 JSON 对象。
- `time_tool` 字段：`operation`、`formatString`、`outputVariable`。`operation` 支持 `now_iso`、`now_epoch`、`format`。
- 安全边界：`mcp_tool` 可通过 `WORKFLOW_MCP_TOOL_ENABLED=False` 降级为 no-op；`time_tool` 可通过 `WORKFLOW_TIME_TOOL_ENABLED=False` 降级为 no-op。工具调用失败时写入空字符串并继续后续节点。

`mcp_tool` 当前已通过 Runtime Toolset Capability 调用工具：`MCPToolsetProvider` 作为薄封装复用 `ToolRegistry` 的全局去重列表和 `MCPClientManager.call_tool()` 的会话执行能力，再经由 `MiddlewarePipeline.run_tool_call()` 进入 `wrap_tool_call` 中间件链。这个链路为工具审计、日志、权限与后续聊天 Agent / 多 Agent 复用预留统一入口。

工具调用会记录轻量运行时事件：`tool.call.started`、`tool.call.finished`、`tool.call.failed`。事件只保存工具名、参数数量、输出长度、content types 和错误摘要，不写入完整工具输出，避免泄露敏感内容。

Runtime Toolset 还提供了内存态的 `ToolPermissionPolicy` 与 `InMemoryToolAuditStore`。当前 workflow 默认使用 `allow_by_default=True`，因此不会改变既有 `mcp_tool` 行为；审计记录只保存工具名、状态、耗时、输出长度、content types 与错误摘要。后续可在此基础上扩展用户级权限、持久化审计和 tool preference。

为对齐 Xpert 的“智能体中间件”画布菜单，后端新增了 `server/xpert_runtime/middleware_registry.py` 与只读接口 `GET /api/runtime/middleware-nodes`。当前 registry 先暴露 5 个可拖拽元数据节点：`system_prompt_injector`、`event_recorder`、`tool_policy`、`tool_audit`、`mcp_tools`。本轮只提供 schema 与 metadata；下一步前端 `NodePalette` 可从该接口拉取分组、字段、图标和搜索内容，渲染“智能体中间件”拖拽菜单。再下一步才会把拖入画布的 `runtime_middleware.xxx` 节点接入 workflow validate 和 runner。

前端 `NodePalette` 已新增“智能体中间件”分组，并从 `/api/runtime/middleware-nodes` 拉取 metadata 渲染内置 middleware 节点。中间件拖拽 payload 使用 JSON 字符串，包含 `kind="runtime_middleware"`、`runtimeMiddlewareId`、`runtimeMiddlewareKind`、`fields` 与 `metadata`；下一步 `WorkflowEditor` 会解析该 payload 并生成可配置的 `runtime_middleware` 节点，再后续接入 NodeConfig 字段表单与 runner 语义。

### 运行时中间件节点（Runtime Middleware Node）

`runtime_middleware` 当前是可视化 + 渐进执行阶段：前端支持从 `NodePalette` 拖拽“智能体中间件”节点到画布，右侧配置面板会根据 `RuntimeMiddlewareField` 动态渲染 `text`、`textarea`、`boolean`、`number`、`select`、`json` 六类基础字段。后端 validate 已最小支持 `runtimeMiddlewareId` 与 `runtimeMiddlewareKind`，classic `workflow_stream` 会为中间件节点发出 `node_delta`，并按已支持的 middleware id 逐步启用真实效果。

`system_prompt_injector` 已具备最小真实执行：节点读取 `runtimeMiddlewareConfig.system_prompt`，先用当前 workflow 变量渲染 `{{variable}}` 模板，再写入运行态上下文；后续 `llm` 节点调用模型时会 prepend 一条 `system` message。若同一条路径上出现多个系统提示词注入器，后执行的节点覆盖前一个。`mcp_tools` 等中间件节点仍保持 no-op 原型，后续再接入 `MiddlewarePipeline` 的真实编排能力。

`tool_policy` 已进入最小真实执行：节点读取 `runtimeMiddlewareConfig.denied_tools`、`allowed_tools` 与 `allow_by_default`，支持换行或逗号分隔工具名，并创建 `ToolPermissionPolicy` 写入 `workflow_runtime_context`。后续 `mcp_tool` 节点优先使用 workflow 级 policy；无 `tool_policy` 节点时回退全局 `workflow_tool_policy`（默认 `allow_by_default=True`）。当 `denied_tools` 命中或 `allow_by_default=False` 且工具不在白名单时，`run_tool_with_runtime` 会抛出 `RuntimeToolError(code="tool_denied")`，classic workflow 记录 error event、写入空输出并继续后续节点。当前作用范围仅 classic workflow 的 `mcp_tool`，不做持久化权限系统或用户级/workspace 级权限。

`event_recorder` 已进入最小真实可见状态：classic workflow 每个 task 会创建独立 `RuntimeEventStore`，`mcp_tool` 节点通过 `MiddlewareContext.store` 将该 store 传入 `MiddlewarePipeline`，因此 `event_recorder.wrap_tool_call` 会记录 `tool.call.started`、`tool.call.finished`、`tool.call.failed`。事件按 `task_id` 隔离，并可通过 `GET /api/workflow/runtime-events/{task_id}` 查询；前端 `WorkflowRun` 的“运行观测”折叠区会展示事件类型、severity、工具名、输出长度和错误摘要。

`tool_audit` 当前是原型可见状态：每个 workflow task 默认拥有独立 `InMemoryToolAuditStore`，工具调用会记录 `tool_name`、`status`、`started_at`、`finished_at`、`duration_ms`、`output_length`、`content_types` 与 `error`。`runtime_middleware.tool_audit` 节点可读取 `runtimeMiddlewareConfig.max_records`，为本次运行重建指定上限的审计 store；观测 API 返回当前 task 的审计记录。该能力仍为内存态，后续再扩展 per-user/per-workspace 过滤、持久化审计与图形化 trace。

### Classic 工作流布局优化

`/workflow` 当前改为“画布 + 单一右侧工作台”的主布局：节点库不再作为常驻左侧长栏，而是在画布标题区提供“节点库”下拉浮层，拖入节点后自动收起；右侧工作台用 `配置 / 运行` tabs 承载 `NodeConfig` 与 `WorkflowRun`。该调整只改变布局，不改变节点数据结构、React Flow 拖拽协议、SSE 运行协议或后端执行逻辑。目标是让节点库、画布和运行结果集中在同一视野附近，避免窄屏或 Docker 本地验收时出现左侧节点库与右侧运行区纵向堆叠、需要大幅下滑的问题。

### Agent Task Runtime（Xpert 对齐）

当前为最小底座原型阶段，主线对齐 Xpert 的 Agent/Handoff/RunRegistry 思路，并在 ModelMirror 内原生实现为 `server/xpert_runtime/agent_tasks.py`。源码策略是“参考协议与分层，原生改写实现”：不迁移 Xpert 的 Nx/NestJS/Angular 主框架，不整文件复制上游源码，也不引入不兼容协议代码。

Agent Task Runtime 包含三层：

- `AgentTask`：任务实体，包含 `title`、`input`、`status`、`result`、`error`、`source_agent`、`assigned_agent`、`metadata` 与时间戳。
- `AgentHandoff`：Agent 间任务移交记录，包含 `source_agent`、`target_agent`、`reason`、`status` 与 metadata。
- `AgentTaskStore`：内存态任务存储，支持 `create/get/list/update/cancel` 与 `create_handoff/list_handoffs`，并将 `agent.task.created`、`agent.task.updated`、`agent.task.cancelled`、`agent.handoff.created` 写入 `RuntimeEventStore`。

后端已开放最小 API：`POST /api/runtime/agent-tasks` 创建任务，`GET /api/runtime/agent-tasks/{task_id}` 查询任务，`POST /api/runtime/agent-tasks/{task_id}/cancel` 取消任务，`GET /api/runtime/agent-tasks` 列出任务。Handoff 最小闭环也已开放：`POST /api/runtime/agent-tasks/{task_id}/handoffs` 创建移交，`GET /api/runtime/agent-tasks/{task_id}/handoffs` 查询任务下的移交记录，`POST /api/runtime/agent-handoffs/{handoff_id}/accept|reject|complete` 更新状态。状态转移限定为 `pending -> accepted/rejected` 与 `accepted -> completed`，非法转移返回 400；每次创建或状态变更会写入 `agent.handoff.created/accepted/rejected/completed` runtime events。当前不做真实多 Agent 编排、不接数据库、不接 Redis/Celery 队列；后续将继续扩展 workflow handoff 节点、handoff queue、agent selection、持久化与前端任务面板。

classic workflow 已新增 `agent_task` 节点，作为 Xpert Agent/Handoff 对齐的第一步闭环。前端可从节点调色板拖入“智能体任务”，配置 `taskTitle`、`taskInput`、`assignedAgent` 与 `outputVariable`；运行时会渲染 `{{变量}}` 模板，调用 `AgentTaskStore.create_task(...)` 创建一条 AgentTask，并将新任务的 `task_id` 写入 `outputVariable`。该节点当前只负责创建任务和输出 ID，不做真实队列分派、专家协作或任务执行；完整任务详情继续通过现有 Agent Task API 查询。

classic workflow 已新增 `workflow_agent` 节点，作为 Xpert Workflow Agent 的最小执行闭环。前端可从节点调色板拖入“工作流智能体”，配置 `agentName`、`modelId`、`rolePrompt`、`taskInput` 与 `outputVariable`；运行时会先渲染 `{{变量}}`，再以 `rolePrompt` 作为该节点 system prompt、`taskInput` 作为用户输入调用现有工作流 LLM 流式函数，最终把模型输出写入 `outputVariable`。该节点会登记 `workflow_agent` 子 run，便于运行观测查看；当前不接 MCP Toolset、不做 Handoff 自动调度、不实现真实多 Agent 协作。

## 2026-06-17 增量：Agent 节点

`agent` 已进入 workflow-native / classic 共享实验线。它不是完整 Dify Agent 复刻，而是 ReAct-Lite MVP：模型要么直接返回答案，要么返回一个 JSON 工具调用决策，运行器再通过全局 MCP 工具注册表调用对应工具。

### 字段

- `agentMode`：`tool_first` 或 `direct`。默认 `tool_first`。
- `instruction`：任务指令，支持 `{{variable}}` 模板。
- `modelId`：调用模型 ID。
- `toolNames`：可选，逗号分隔的工具白名单；留空代表全部已注册工具。
- `outputVariable`：Agent 最终输出变量。
- `maxIterations`：工具循环上限，默认 5，运行器最多允许 20。
- `temperature`：模型温度，范围 0-2。
- `promptSuffix`：可选补充提示词，支持 `{{variable}}` 模板。

### 安全边界

- `agent` 可通过 `WORKFLOW_AGENT_ENABLED=False` 降级为 no-op。
- `tool_first` 模式依赖 `/mcps` 已连接的 MCP Server；没有可用工具时会切换到直接回答。
- 未配置 API Key、模型调用失败或工具调用失败时，运行器发出 `error` 事件并写入空字符串，不中断后续节点。
- 当前只支持单 Agent 节点内的轻量工具循环，不实现复杂多 Agent 协作、记忆、长期任务或持久化运行态。

## 回退方案

如果 native 实验页影响体验：

1. 从 `client/src/App.tsx` 移除 `/workflow-native` 路由。
2. 从 `client/src/data/studio.ts` 移除实验卡片。
3. 后端可以保留 `/api/workflow-native/validate`，因为它不会影响稳定路径。
4. `/workflow`、`/workflow/classic`、`/rag` 不需要变更。
