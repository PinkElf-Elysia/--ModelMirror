# 后端架构与 API 文档

最后更新日期：2026-06-17
维护人：模镜团队

## 技术栈

- Python 3.11+
- FastAPI
- Pydantic
- httpx
- ChromaDB
- MCP Python SDK
- Uvicorn

## 目录结构

```text
server/
├── main.py                 # FastAPI 应用、聊天、工作流、MCP、Skill、RAG 聚合入口
├── api/                    # 独立路由
├── data/                   # 后端静态数据
├── mcp/                    # MCP stdio 客户端管理器
├── rag/                    # 本地 RAG 服务
├── registry/               # 工具注册表
├── skills/                 # Skill 管理
├── workflow_native/        # workflow-native schema 和 validate
└── requirements.txt
```

## 环境变量

| 变量 | 必填 | 说明 |
| --- | --- | --- |
| `LLM_GATEWAY_URL` | 推荐 | newAPI 或其他 OpenAI 兼容网关地址，例如 `http://localhost:3000/v1/chat/completions`。 |
| `LLM_GATEWAY_KEY` | 推荐 | newAPI 网关统一 API Key。 |
| `OPENROUTER_API_KEY` | 回退 | 未配置 newAPI 时直接访问 OpenRouter。 |
| `ALLOWED_ORIGINS` | 否 | CORS 白名单。 |
| `OPENROUTER_TEXT_FALLBACK_MODEL` | 否 | 文本回退模型。 |
| `OPENROUTER_VISION_FALLBACK_MODEL` | 否 | 多模态回退模型。 |
| `RAG_STORAGE_DIR` | 否 | RAG 存储目录。 |
| `RAG_UPLOAD_DIR` | 否 | RAG 上传目录。 |

优先级：

1. `LLM_GATEWAY_URL` + `LLM_GATEWAY_KEY`
2. `OPENROUTER_API_KEY`
3. 都未配置时，聊天接口返回网关未配置错误。

## API

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

OpenAI 兼容流式聊天代理。请求体使用 `model_id` 和 `messages`，响应为 `text/event-stream`。

文本请求：

```bash
curl -N -X POST http://localhost:8000/api/chat ^
  -H "Content-Type: application/json" ^
  -d "{\"model_id\":\"openai/gpt-4o-mini\",\"messages\":[{\"role\":\"user\",\"content\":\"你好\"}],\"temperature\":0.7,\"max_tokens\":1024}"
```

多模态输入：

```json
{
  "role": "user",
  "content": [
    {"type": "text", "text": "描述这张图"},
    {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,..."}}
  ]
}
```

图片生成输出兼容：

- 上游可能返回 `choices[0].delta.content` 字符串。
- 上游可能返回 `choices[0].delta.content` 多模态 parts。
- 上游可能返回 `choices[0].delta.images` 或 `choices[0].message.images`。
- 图片 part 中的 `image_url.url` 可能是 `https://...`，也可能是 `data:image/...`。

后端内部流式 helper `sse_delta_text(event_text: str) -> list[str]` 会把多模态图片 part 规范化为 `![图片](URL)` 文本片段，供 workflow/Fusion/team 等复用。`/api/chat` 主代理保持 OpenAI SSE 兼容转发，前端 `fetchChatStream` 会做同样的图片 part 解析。

图片生成模型冒烟：

```bash
curl -N -X POST http://localhost:8000/api/chat ^
  -H "Content-Type: application/json" ^
  -d "{\"model_id\":\"recraft/recraft-v3\",\"messages\":[{\"role\":\"user\",\"content\":\"画一只猫\"}]}"
```

预期：SSE 中可以观察到 `image_url` 或 `data:image/...`，前端显示图片卡片。

### POST `/api/workflow/run`

经典自研工作流执行接口，供 `/workflow` 使用。

```bash
curl -N -X POST http://localhost:8000/api/workflow/run ^
  -H "Content-Type: application/json" ^
  -d "{\"workflow\":{\"id\":\"draft\",\"title\":\"测试\",\"nodes\":[{\"id\":\"input\",\"type\":\"input\",\"data\":{\"variableName\":\"user_input\"}},{\"id\":\"output\",\"type\":\"output\",\"data\":{\"variableName\":\"user_input\"}}],\"edges\":[{\"id\":\"e1\",\"source\":\"input\",\"target\":\"output\"}]},\"inputs\":{\"user_input\":\"hello\"}}"
```

### GET `/api/workflow-native/templates`

返回 workflow-native 实验模板。

```bash
curl http://localhost:8000/api/workflow-native/templates
```

### POST `/api/workflow-native/validate`

静态校验 workflow-native 图结构，不执行模型、RAG、MCP 或外部 HTTP。

```bash
curl -X POST http://localhost:8000/api/workflow-native/validate ^
  -H "Content-Type: application/json" ^
  -d "{\"workflow\":{\"id\":\"draft\",\"title\":\"t\",\"nodes\":[],\"edges\":[]}}"
```

### MCP / RAG / Skill

详细说明见：

- [MCP_INTEGRATION.md](./MCP_INTEGRATION.md)
- [RAG_INTEGRATION.md](./RAG_INTEGRATION.md)
- [SKILL_INTEGRATION.md](./SKILL_INTEGRATION.md)

## 验证

```bash
python -m py_compile server/main.py
python -m pytest server/tests/ -q
```
