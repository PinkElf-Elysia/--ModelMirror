# workflow-native 自研工作流设计

workflow-native 是模镜自研工作流引擎的渐进式实验线。它不会替换当前稳定的 `/workflow` Dify iframe 入口，也不会改动 `/rag`。当前阶段提供静态图校验能力，并在 classic 运行器中试点少量本地节点执行，让团队先把数据模型、API 契约、错误模型和测试流程立起来。

最后更新日期：2026-06-16  
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
| `http_request` | `http-request` | native 仅支持 GET/POST 文本响应，默认关闭真实出站请求。 |
| `list_operation` | `list-operator` | native 当前基于逗号分隔字符串，尚无完整数组变量系统。 |
| `iteration` | `iteration` | native 当前只做节点内迭代，不执行跨节点子图。 |
| `output` | `end` / `answer` | native 输出指定变量，Dify 支持更丰富的结束响应。 |

参考点：Dify 工作流由节点、边、变量和运行态组成；native 当前只借鉴节点概念、拓扑顺序和静态校验分类，不复制 Dify 源码实现。

暂不接入的节点：`agent`、问题理解、问题分类器、工具、人工介入。这些能力分别依赖 Agent 编排、异步人工回调或 MCP 工具协议，需要独立设计文档和测试护栏后再进入 native 实验线。

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

## 回退方案

如果 native 实验页影响体验：

1. 从 `client/src/App.tsx` 移除 `/workflow-native` 路由。
2. 从 `client/src/data/studio.ts` 移除实验卡片。
3. 后端可以保留 `/api/workflow-native/validate`，因为它不会影响稳定路径。
4. `/workflow`、`/workflow/classic`、`/rag` 不需要变更。
