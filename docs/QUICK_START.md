# 5 分钟快速上手

## 环境要求

- Node.js 18+，当前项目使用 Vite 7。
- Python 3.11+，后端使用 FastAPI。
- Docker / Docker Compose：可选，用于运行 Dify 社区版或项目容器。
- Git：用于版本控制。

## 克隆与安装

```bash
git clone <your-private-repo-url> model-mirror
cd model-mirror
```

安装前端依赖：

```bash
cd client
npm install
cd ..
```

安装后端依赖：

```bash
cd server
python -m pip install -r requirements.txt
cd ..
```

## 配置环境变量

```bash
copy server\.env.example server\.env
copy client\.env.example client\.env
```

编辑 `server/.env`：

```bash
OPENROUTER_API_KEY=sk-or-v1-your-key
ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
OPENROUTER_HTTP_REFERER=http://localhost:5173
OPENROUTER_APP_TITLE=ModelMirror
OPENROUTER_TEXT_FALLBACK_MODEL=deepseek/deepseek-chat
OPENROUTER_VISION_FALLBACK_MODEL=qwen/qwen2.5-vl-72b-instruct
DIFY_API_BASE_URL=http://localhost:5001/v1
DIFY_API_KEY=app-your-dify-api-key
```

编辑 `client/.env`：

```bash
VITE_DIFY_WEB_URL=http://localhost:3000
```

> 没有 Dify API Key 时，模型浏览和聊天仍可运行；`/workflow` 和 `/rag` 会显示 iframe 壳，但 Dify 内部能力需要本地 Dify 服务。

## 启动后端

```bash
cd server
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

验证：

```bash
curl http://localhost:8000/api/health
curl http://localhost:8000/api/dify/health
```

期望：

```json
{"status":"ok"}
```

`/api/dify/health` 如果未配置 key 会返回：

```json
{"status":"missing_api_key","base_url":"http://localhost:5001/v1"}
```

## 启动前端

```bash
cd client
npm run dev -- --host 0.0.0.0 --port 5173
```

访问：

```text
http://localhost:5173/models
```

## 可选：启动 Dify

按照 Dify 官方 Docker Compose 文档启动社区版，确保：

- Dify Web：`http://localhost:3000`
- Dify API：`http://localhost:5001/v1`

在 Dify 中创建工作空间和应用后，将 App API Key 写入 `server/.env` 的 `DIFY_API_KEY`。

## 页面验证清单

| 页面 | 地址 | 期望 |
| --- | --- | --- |
| 模型招聘会 | `http://localhost:5173/models` | 能看到模型卡片和筛选。 |
| AI 人才市场 | `http://localhost:5173/agents` | 能看到智能体卡片。 |
| 面试间 | `http://localhost:5173/chat/openai%2Fgpt-4o-mini` | 能输入消息，后端配置正确时可流式回复。 |
| MCP 工具采购 | `http://localhost:5173/mcps` | 能看到 MCP 项目卡片。 |
| Skill 技能货架 | `http://localhost:5173/skills` | 能看到 Skill 项目卡片。 |
| Dify 工作流 | `http://localhost:5173/workflow` | 能看到 Dify iframe 工作流入口。 |
| Dify 资料库 | `http://localhost:5173/rag` | 能看到 Dify iframe 知识库入口。 |

## 常用检查命令

```bash
cd client
npm run build
```

```bash
cd ..
python -m py_compile server/main.py server/api/dify_proxy.py
```

最后更新日期：2026-06-10  
维护人：模镜团队
