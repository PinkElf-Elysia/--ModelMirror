# 后端架构与 API 文档

## 技术栈

- Python 3.11+
- FastAPI
- Pydantic
- httpx
- python-dotenv
- Uvicorn

## 目录结构

```text
server/
├── main.py                 # 主 FastAPI 应用、聊天、Fusion、团队、经典工作流接口
├── api/
│   ├── __init__.py
│   └── dify_proxy.py       # /api/dify/* 代理
├── data/
│   └── agents.json         # 后端自动路由和团队协作使用的智能体数据
├── requirements.txt
└── .env.example
```

## 中间件与通用能力

- CORS：允许本地 Vite 开发服务器访问。
- 速率限制：简单内存窗口，同一 IP 每分钟最多 20 次聊天请求。
- 内容检查：基础敏感关键词拦截。
- 流式响应：聊天、Fusion、团队协作和工作流均使用 SSE 或 SSE-like 文本流。

## 环境变量

| 变量 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `LLM_GATEWAY_URL` | 推荐 | `http://localhost:3000/v1/chat/completions` | newAPI 或其他 OpenAI 兼容 LLM 网关地址。 |
| `LLM_GATEWAY_KEY` | 推荐 | 空 | newAPI 网关统一 API Key。 |
| `OPENROUTER_API_KEY` | 回退 | 空 | 直接访问 OpenRouter 的回退密钥，向后兼容。 |
| `ALLOWED_ORIGINS` | 否 | 本地 5173/5174 | CORS 白名单。 |
| `OPENROUTER_HTTP_REFERER` | 否 | `http://localhost:5173` | 请求 OpenRouter 的 Referer。 |
| `OPENROUTER_APP_TITLE` | 否 | `ModelMirror` | 请求 OpenRouter 的应用名。 |
| `OPENROUTER_TEXT_FALLBACK_MODEL` | 否 | `deepseek/deepseek-chat` | 文本回退模型。 |
| `OPENROUTER_VISION_FALLBACK_MODEL` | 否 | `qwen/qwen2.5-vl-72b-instruct` | 多模态回退模型。 |
| `OPENROUTER_JUDGE_MODEL` | 否 | `openai/gpt-4o` | Fusion 裁判模型。 |
| `DIFY_API_BASE_URL` | 否 | `http://localhost:5001/v1` | Dify API 地址。 |
| `DIFY_API_KEY` | Dify 功能需要 | 空 | Dify App API Key。 |

## LLM 网关配置

模镜支持通过 newAPI 网关统一管理多个 AI 服务商。后端所有 OpenAI 兼容 Chat Completions 调用会先读取 `LLM_GATEWAY_URL` 和 `LLM_GATEWAY_KEY`；如果二者都存在，则请求 newAPI；否则回退到 `OPENROUTER_API_KEY` 和 OpenRouter 官方地址。

优先级：

1. `LLM_GATEWAY_URL` + `LLM_GATEWAY_KEY`：使用 newAPI 或其他 OpenAI 兼容网关。
2. `OPENROUTER_API_KEY`：回退为直接访问 OpenRouter。
3. 都未配置：接口返回 `LLM 网关未配置，请设置环境变量 LLM_GATEWAY_KEY 或 OPENROUTER_API_KEY。`

本地示例：

```bash
LLM_GATEWAY_URL=http://localhost:3000/v1/chat/completions
LLM_GATEWAY_KEY=your-new-api-key
OPENROUTER_API_KEY=your-openrouter-key
```

Docker Compose 已包含 `new-api` 服务。容器内 server 使用服务名访问网关：

```bash
docker compose -p modelmirror up -d --build
```

启动后可访问 `http://localhost:3000` 进入 newAPI 管理界面，创建统一 API Key 后写入 `server/.env` 或部署环境变量。若暂不使用 newAPI，可不配置 `LLM_GATEWAY_KEY`，继续使用 `OPENROUTER_API_KEY` 回退。

## API 端点

### GET `/api/health`

健康检查。

```bash
curl http://localhost:8000/api/health
```

响应：

```json
{"status":"ok"}
```

### POST `/api/chat`

流式聊天接口，代理 OpenAI 兼容 Chat Completions。默认优先走 newAPI 网关，未配置网关时回退 OpenRouter。

请求：

```bash
curl -N -X POST http://localhost:8000/api/chat ^
  -H "Content-Type: application/json" ^
  -d "{\"model_id\":\"openai/gpt-4o-mini\",\"messages\":[{\"role\":\"user\",\"content\":\"你好\"}],\"temperature\":0.7,\"top_p\":1,\"max_tokens\":1024}"
```

请求体字段：

```json
{
  "model_id": "openai/gpt-4o-mini",
  "messages": [
    {"role": "user", "content": "你好"}
  ],
  "temperature": 0.7,
  "top_p": 1,
  "max_tokens": 2048,
  "seed": null,
  "stop": null
}
```

多模态消息使用 OpenAI Vision 兼容格式：

```json
{
  "role": "user",
  "content": [
    {"type": "text", "text": "描述这张图"},
    {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,..."}}
  ]
}
```

响应：`text/event-stream`，数据格式兼容 OpenAI SSE。

错误响应示例：

```json
{"error":"模型暂时不可用，请稍后重试。"}
```

### POST `/api/workflow/run`

经典自研工作流 MVP 执行接口。主路径已回退 Dify，此接口保留给 `/workflow/classic`。

```bash
curl -N -X POST http://localhost:8000/api/workflow/run ^
  -H "Content-Type: application/json" ^
  -d "{\"workflow\":{\"id\":\"draft\",\"title\":\"测试\",\"nodes\":[{\"id\":\"input\",\"type\":\"input\",\"data\":{\"variableName\":\"user_input\"}},{\"id\":\"output\",\"type\":\"output\",\"data\":{\"variableName\":\"user_input\"}}],\"edges\":[{\"id\":\"e1\",\"source\":\"input\",\"target\":\"output\"}]},\"inputs\":{\"user_input\":\"hello\"}}"
```

响应：SSE 事件，包括 `node_start`、`node_end`、`workflow_end`、`error`。

运行流第一条 SSE 事件为 `workflow_meta`，包含 `task_id`。遇到 `human_intervention` 节点时，运行器发送 `human_intervention_pending` 并暂停，直到收到 resume 请求。

### POST `/api/workflow/run/{task_id}/resume`

继续处于人工介入等待状态的 classic 工作流任务。

```bash
curl -X POST http://localhost:8000/api/workflow/run/<task_id>/resume ^
  -H "Content-Type: application/json" ^
  -d "{\"node_id\":\"human\",\"input_text\":\"确认继续\"}"
```

响应示例：

```json
{"ok":true,"task_id":"...","node_id":"human"}
```

### GET `/api/workflow/run/{task_id}/status`

查询 classic 工作流任务是否正在等待人工输入。任务只保存在内存中，默认 TTL 为 30 分钟。

```bash
curl http://localhost:8000/api/workflow/run/<task_id>/status
```

响应示例：

```json
{
  "task_id": "...",
  "paused": true,
  "paused_node_id": "human",
  "created_at": 1780000000.0,
  "ttl_seconds_left": 1790.0
}
```

### GET `/api/workflow-native/templates`

自研工作流 native 实验线的模板接口。当前返回一个三节点线性样例，供 `/workflow-native` 做静态校验演示。

```bash
curl http://localhost:8000/api/workflow-native/templates
```

### POST `/api/workflow-native/validate`

自研工作流 native 静态图校验接口。该接口不执行模型、代码、Tool 或 RAG，只校验节点、连线、变量引用和拓扑顺序。图校验失败时 HTTP 仍返回 `200`，通过 `valid=false` 和 `issues` 表达问题。

当前支持的 native 节点：`input`、`llm`、`condition`、`code`、`variable_assign`、`template_transform`、`variable_aggregator`、`parameter_extractor`、`knowledge_retrieval`、`document_extractor`、`human_intervention`、`http_request`、`list_operation`、`iteration`、`output`。

合法三节点样例：

```bash
curl -X POST http://localhost:8000/api/workflow-native/validate ^
  -H "Content-Type: application/json" ^
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

详细设计见 [workflow-native-design.md](./workflow-native-design.md)。

### `/api/mcp/*`

MCP 原生 stdio 集成接口。详细说明见 [MCP_INTEGRATION.md](./MCP_INTEGRATION.md)。

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/mcp/connect` | 启动 MCP Server 并创建 session。 |
| GET | `/api/mcp/sessions` | 获取所有活跃 MCP session 摘要。 |
| GET | `/api/mcp/{session_id}/tools` | 获取该 session 暴露的工具列表。 |
| POST | `/api/mcp/{session_id}/call` | 调用指定 MCP 工具。 |
| DELETE | `/api/mcp/{session_id}` | 断开连接并清理子进程。 |
| GET | `/api/registry/tools` | 获取全局 MCP 工具注册表，重名工具按首次出现保留。 |

示例：

```bash
curl -X POST http://localhost:8000/api/mcp/connect ^
  -H "Content-Type: application/json" ^
  -d "{\"server_command\":[\"npx\",\"-y\",\"@playwright/mcp@latest\"]}"
```

### POST `/api/fusion/chat`

模型 Fusion 接口。后端并行调用 2-5 个模型，再由裁判模型汇总。

```bash
curl -N -X POST http://localhost:8000/api/fusion/chat ^
  -H "Content-Type: application/json" ^
  -d "{\"model_ids\":[\"deepseek/deepseek-chat\",\"openai/gpt-4o-mini\"],\"messages\":[{\"role\":\"user\",\"content\":\"给我三个产品命名方向\"}],\"judge_model_id\":\"openai/gpt-4o\"}"
```

响应：SSE，包含候选模型输出和最终综合意见。

### POST `/api/route-agent`

自动路由到最合适的智能体角色。

```bash
curl -N -X POST http://localhost:8000/api/route-agent ^
  -H "Content-Type: application/json" ^
  -d "{\"message\":\"帮我检查这个 API 的安全风险\",\"model_id\":\"deepseek/deepseek-chat\",\"top_k\":3}"
```

响应：SSE，先返回匹配到的专家，再返回模型回复。

### POST `/api/team/chat`

AI Team 串行或辩论式协作。

```bash
curl -N -X POST http://localhost:8000/api/team/chat ^
  -H "Content-Type: application/json" ^
  -d "{\"members\":[{\"agent_id\":\"security-engineer\"},{\"agent_id\":\"product-manager\"}],\"message\":\"评审一个登录功能\",\"model_id\":\"deepseek/deepseek-chat\",\"mode\":\"serial\"}"
```

响应：SSE，包含每个专家输出和最终综合意见。

### GET `/api/dify/health`

Dify 代理配置检查。

```bash
curl http://localhost:8000/api/dify/health
```

响应：

```json
{"status":"configured","base_url":"http://localhost:5001/v1"}
```

未配置 Dify Key 时：

```json
{"status":"missing_api_key","base_url":"http://localhost:5001/v1"}
```

### GET `/api/dify/apps`

获取 Dify 应用列表。需要 `DIFY_API_KEY`。

```bash
curl http://localhost:8000/api/dify/apps
```

### POST `/api/dify/workflow/run`

转发到 Dify `/v1/workflows/run`，默认 `response_mode=streaming`。

```bash
curl -N -X POST http://localhost:8000/api/dify/workflow/run ^
  -H "Content-Type: application/json" ^
  -d "{\"inputs\":{\"query\":\"你好\"},\"user\":\"local-dev\"}"
```

### `/api/dify/{path:path}`

通用 Dify API 代理。仅在必要时使用，避免前端直接持有 Dify Key。

## 如何添加新的 API 端点

1. 在 `server/main.py` 中定义 Pydantic 请求模型。
2. 实现处理函数并显式捕获 `httpx.HTTPError`。
3. 若返回流式数据，使用 `StreamingResponse`。
4. 不要在响应或日志中输出 API Key。
5. 更新本文档和 [QUICK_START.md](./QUICK_START.md)。

最后更新日期：2026-06-16
维护人：模镜团队
