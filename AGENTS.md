# AGENTS.md - 模镜协作与 Harness Engineering 规则

本文件是模镜仓库内 AI Agent、人类开发者和自动化任务的项目级操作说明。任何代码生成、重构、测试、提交和发布都必须优先遵守本文档。

最后更新日期：2026-06-17  
维护人：模镜团队

## 1. 项目边界

模镜 ModelMirror 是 AI 资源浏览与协作平台，当前主要模块包括：

- 前端：React + TypeScript + Tailwind CSS + Vite。
- 后端：FastAPI + httpx + Pydantic。
- 模型调用：优先通过 `LLM_GATEWAY_URL` / `LLM_GATEWAY_KEY` 接入 newAPI 或其他 OpenAI 兼容网关，未配置时回退 OpenRouter。
- 聊天：`/api/chat` 使用 SSE，支持文本、多模态输入和图片生成模型输出。
- 工作流：`/workflow` 是经典自研 React Flow 画布；`/workflow-native` 是实验线。
- RAG：`/rag` 是本地资料库与检索增强页面。
- 设置：`/settings` 内嵌 newAPI 控制台。
- 资源页：模型、智能体、MCP、Skill、提示词、专家团。

稳定入口：

- `/models`
- `/agents`
- `/chat/:modelId`
- `/workflow`
- `/workflow-native`
- `/rag`
- `/mcps`
- `/skills`
- `/settings`

## 2. Harness Engineering 原则

Harness Engineering 的意思是：先搭护栏，再做功能。任何变更都必须有明确范围、验证方式、回退路径和可观测结果。

强制原则：

1. 小步交付：一次只改一个可验证目标。
2. 先读代码：实现前必须确认真实文件、接口和数据结构。
3. 先定义验收：每个任务必须有可运行的 acceptance check。
4. 稳定路径优先：实验功能不得替换主入口，除非用户明确要求并完成验证。
5. 可回退：影响主路径的变更必须写明回退方案。
6. 不泄密：不得提交 `.env`、API Key、token、日志中的敏感信息。
7. 不破坏：不得重置、删除或回滚用户未授权的文件。

## 3. 红线

严禁：

- 将真实 `OPENROUTER_API_KEY`、`LLM_GATEWAY_KEY`、`DIFY_API_KEY`、GitHub token 写入仓库。
- 在前端代码中硬编码后端密钥。
- 未测试通过就修改 `/api/chat`、`/workflow`、`/rag` 等主路径。
- 使用不安全批量替换处理中文源码。
- 提交 `node_modules/`、`client/dist/`、日志、临时目录、RAG 存储数据和 Docker 持久化数据。
- 为了“快速修复”禁用类型检查、安全检查或输入校验。

## 4. 推荐工作流

每次任务按以下顺序推进：

1. Inspect：读取相关文件、路由、接口和测试。
2. Plan：列出变更范围和验收命令。
3. Implement：小步修改，避免无关重构。
4. Verify：运行最小必要检查。
5. Document：更新 README、模块文档、术语表或 harness。
6. Commit：使用清晰提交信息。

## 5. 验证命令

前端：

```bash
cd client
npm.cmd run build
```

后端语法：

```bash
python -m py_compile server/main.py
```

后端测试：

```bash
python -m pytest server/tests/ -q
```

Docker Compose：

```bash
docker compose -p modelmirror up -d --build --force-recreate
docker ps
```

健康检查：

```bash
curl http://localhost:8000/api/health
curl http://localhost:5173/models
```

## 6. `/api/chat` 与图片输出规则

聊天链路是高风险主路径。修改以下文件时必须同步验证：

- `server/main.py`
- `client/src/utils/fetchChatStream.ts`
- `client/src/pages/ChatPage.tsx`
- `client/src/utils/extractImages.ts`

规则：

- 不新增不必要的 SSE 事件类型；优先兼容 OpenAI SSE 的 `choices[0].delta` / `choices[0].message`。
- 纯文本模型的流式追加行为不得改变。
- 图片生成模型可能返回：
  - `content` 字符串
  - `content` 多模态 parts
  - `delta.images`
  - `message.images`
  - `image_url.url`
  - `data:image/...`
- 接收到图片 URL 时统一转换为 `![图片](URL)` 或等价图片卡片，让 `ChatPage` 走已有 Lightbox。
- 用户上传图片的发送逻辑和 `message.images` 展示逻辑不得被破坏。

图片输出验收：

```bash
curl -N -X POST http://localhost:8000/api/chat ^
  -H "Content-Type: application/json" ^
  -d "{\"model_id\":\"recraft/recraft-v3\",\"messages\":[{\"role\":\"user\",\"content\":\"画一只猫\"}]}"
```

预期：响应中可观察到 `image_url` 或 `data:image/...`；前端 `/chat/recraft%2Frecraft-v3` 中出现可点击图片，点击后进入 Lightbox。

## 7. workflow-native 增量规则

workflow-native 是实验线。任何新增节点、运行器分支或校验规则必须遵守：

- 前端节点类型、后端 `NativeNodeKind`、validate 规则、测试用例和文档必须同步更新。
- `/api/workflow-native/validate` 只做静态校验，不调用模型、RAG、MCP 或外部 HTTP。
- 涉及外部请求、文件读取、模型调用的节点必须有默认关闭或安全降级路径。
- 每新增一类节点至少补一条合法样例和一条非法样例测试。

## 8. MCP 开发规则

MCP 原生集成属于后端进程管理和工具执行能力，开发时必须：

- 后端代码放在 `server/mcp/` 包内。
- 使用官方 `mcp` Python SDK 的 `ClientSession` 抽象。
- MCP Server 工作目录限制在 `server/mcp/sandboxes/`。
- 校验 `server_command`，禁止 shell 拼接和特殊字符注入。
- 连接必须有超时、断开、重试和清理逻辑。
- 前端从 `client/src/data/mcpProjects.ts` 读取命令，不硬编码命令。

## 9. Git 规范

提交前必须确认：

```bash
git status --short
git diff --cached --name-only
```

提交信息：

```text
type: 简短中文说明
```

示例：

```text
fix: 修复图片生成模型输出显示
docs: 更新聊天图片输出 harness
feature: 添加 MCP stdio 客户端管理器
```

## 10. 交付格式

最终回复应包含：

- 改动摘要
- 文件列表
- 验证命令与结果
- 未完成项或阻塞
- 风险和回退建议
