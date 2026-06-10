# 模镜 ModelMirror

模镜是一个多资源 AI 浏览器，包含模型招聘会、AI 人才市场、MCP 工具招领、Skill 技能货架、提示词市场、面试间、专家团，以及通过 Dify 稳定接入的工作流和 RAG 资料库。

## 当前稳定能力

- 模型招聘会：模型筛选、人民币价格换算、聊天入口和多模态对话。
- AI 人才市场：智能体角色浏览、面试入口和专家团能力。
- MCP / Skill：首批工具与技能项目陈列。
- 面试间：Markdown、图片输入、提示词助手、超级提示词模式和高级参数面板。
- 工作流：通过 Dify 社区版 iframe 嵌入，提供成熟工作流编辑、调试和发布能力。
- RAG 资料库：通过 Dify 知识库管理文档上传、切分、检索测试和知识库问答。

## 环境变量

复制示例文件后填写：

```bash
copy server\.env.example server\.env
copy client\.env.example client\.env
```

`server/.env` 至少需要：

```bash
OPENROUTER_API_KEY=你的模型网关密钥
ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
OPENROUTER_HTTP_REFERER=http://localhost:5173
OPENROUTER_APP_TITLE=ModelMirror
DIFY_API_BASE_URL=http://localhost:5001/v1
DIFY_API_KEY=你的 Dify App API Key
```

`client/.env`：

```bash
VITE_DIFY_WEB_URL=http://localhost:3000
```

## 启动 Dify

请按 Dify 官方 Docker Compose 方式启动社区版，并确保：

- Dify Web 可通过 `http://localhost:3000` 访问。
- Dify API 可通过 `http://localhost:5001/v1` 访问。
- 在 Dify 中创建工作空间和应用，获取可用于工作流 / 知识库的 API Key。

## 启动后端

```bash
cd server
python -m pip install -r requirements.txt
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

健康检查：

```bash
curl http://localhost:8000/api/health
curl http://localhost:8000/api/dify/health
```

## 启动前端

```bash
cd client
npm install
npm run dev -- --host 0.0.0.0 --port 5173
```

打开：

```text
http://localhost:5173/models
```

稳定工作流入口：

```text
http://localhost:5173/workflow
```

稳定资料库入口：

```text
http://localhost:5173/rag
```

## Docker Compose

```bash
docker compose -p modelmirror up --build -d
```

停止：

```bash
docker compose -p modelmirror down
```

## 工程治理

自研工作流替代路线已暂停。后续必须先完成设计文档、接口契约和测试，再在 `/workflow-native` 之类的独立路由中与 Dify 稳定版本并行验证。
