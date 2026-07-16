<!-- context7 -->
Use Context7 MCP to fetch current documentation whenever the user asks about a library, framework, SDK, API, CLI tool, or cloud service -- even well-known ones like React, Next.js, Prisma, Express, Tailwind, Django, or Spring Boot. This includes API syntax, configuration, version migration, library-specific debugging, setup instructions, and CLI tool usage. Use even when you think you know the answer -- your training data may not reflect recent changes. Prefer this over web search for library docs.

Do not use for: refactoring, writing scripts from scratch, debugging business logic, code review, or general programming concepts.

## Steps

1. Always start with `resolve-library-id` using the library name and the user's question, unless the user provides an exact library ID in `/org/project` format.
2. Pick the best match (ID format: `/org/project`) by exact name match, description relevance, code snippet count, source reputation, and benchmark score. Use version-specific IDs when the user mentions a version.
3. `query-docs` with the selected library ID and the user's full question.
4. Answer using the fetched docs.
<!-- context7 -->

--- project-doc ---

# AGENTS.md - 模镜协作与 Harness Engineering 规则

本文件是模镜仓库内 AI Agent、人类开发者和自动化任务的项目级操作说明。任何代码生成、重构、测试、提交和发布都必须优先遵守本文档。

最后更新日期：2026-07-15
维护人：模镜团队

## 1. 项目边界

模镜 ModelMirror 是 AI 资源浏览与协作平台，当前主要模块包括：

- 前端：React + TypeScript + Tailwind CSS + Vite。
- 后端：FastAPI + httpx + Pydantic。
- 模型调用：优先通过 `LLM_GATEWAY_URL` / `LLM_GATEWAY_KEY` 接入 newAPI 或其他 OpenAI 兼容网关，未配置时回退 OpenRouter。
- 聊天：`/api/chat` 使用 SSE，支持文本、多模态输入和图片生成模型输出。
- 智能体：`/agents` 是智能体入口，`/agents/studio` 管理可保存、版本化发布的 Xpert，`/agents/meta-agent` 是元智能体任务工作台。
- 工作流：`/workflow` 默认使用经典自研 React Flow 画布，`/workflow-native` 是实验线。
- 协作 Runtime：AgentTask、HandoffExecutor、Conversation Goal 与 RunRegistry 共同提供单进程文件型协作闭环。
- RAG：`/rag` 是本地资料库、版本化 Knowledge Pipeline 与检索增强页面。
- 上下文：Xpert Chat 支持会话附件、文件理解、显式记忆和待确认记忆候选。
- 运行观测：`/runtime` 聚合 MCP、Tool Registry、RunRegistry、Skill 和脱敏环境状态。
- 设置：`/settings` 内嵌 newAPI 控制台。
- 资源页：模型、智能体、MCP、Skill、提示词、专家团。

稳定入口：

- `/models`
- `/agents`
- `/agents/meta-agent`
- `/agents/studio`
- `/agents/goals`
- `/agents/xpert/:xpertId/chat`
- `/apps/:appSlug`
- `/chat/:modelId`
- `/workflow`
- `/workflow-native`
- `/rag`
- `/mcps`
- `/skills`
- `/studio`
- `/toolsets`
- `/runtime`
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

后端语法（按变更模块补充显式文件）：

```bash
python -m py_compile server/main.py server/rag/*.py server/xpert_runtime/*.py server/workflow_native/*.py server/xperts/*.py
```

重点测试：

```bash
python -m pytest server/tests/test_meta_agent.py -q
python -m pytest server/tests/test_xpert_runtime_foundation.py -q
python -m pytest server/tests/test_xpert_runtime_chat.py -q
python -m pytest server/tests/test_xpert_runtime_toolset.py -q
python -m pytest server/tests/test_xpert_publish.py -q
python -m pytest server/tests/test_xpert_handoff_executor.py -q
python -m pytest server/tests/test_xpert_conversation_goals.py -q
python -m pytest server/tests/test_xpert_context.py -q
python -m pytest server/tests/test_rag_pipeline.py -q
python -m pytest server/tests/test_rag_pipeline_execute.py -q
python -m pytest server/tests/test_rag_retrieval_v2.py -q
python -m pytest server/tests/test_xpert_app_api.py -q
```

全量后端测试：

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
curl http://localhost:5173/studio
```

容器内 MCP 安装运行时检查：

```bash
docker compose -p modelmirror exec server node --version
docker compose -p modelmirror exec server npm --version
docker compose -p modelmirror exec server npx --version
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
- 图片生成模型可能返回 `content` 字符串、多模态 parts、`delta.images`、`message.images`、`image_url.url` 或 `data:image/...`。
- 接收到图片 URL 时统一转换为 `![图片](URL)` 或等价图片卡片，让 `ChatPage` 走已有 Lightbox。
- 用户上传图片的发送逻辑和 `message.images` 展示逻辑不得被破坏。

## 7. workflow-native 与经典工作流规则

workflow-native 是实验线。经典工作流是 `/workflow` 默认入口。任何新增节点、运行器分支或校验规则必须遵守：

- 前端节点类型、后端 `NativeNodeKind`、validate 规则、测试用例和文档必须同步更新。
- `/api/workflow-native/validate` 只做静态校验，不调用模型、RAG、MCP 或外部 HTTP。
- 涉及外部请求、文件读取、模型调用的节点必须有默认关闭或安全降级路径。
- 每新增一类节点至少补一条合法样例和一条非法样例测试。
- 工作流执行面板应按节点聚合 `node_delta`，不得把同一节点的流式片段无限堆成大量独立卡片。
- React Flow Controls 在深色画布上必须保持图标可见；修改 `client/src/index.css` 后需在 `/workflow` 手动检查。

## 8. 元智能体规则

元智能体用于把自然语言目标拆解为可编辑的经典工作流草稿。

- 前端入口：`/agents/meta-agent`。
- 后端接口：`POST /api/meta-agent/generate-workflow`。
- 后端实现放在 `server/meta_agent/`，不得把 planner 逻辑继续堆进 `server/main.py`。
- 元智能体生成的 workflow 必须经过 `workflow_native.validate_workflow_graph` 校验后再返回。
- Docker 镜像必须复制 `server/meta_agent/`，否则容器会因 `ModuleNotFoundError: meta_agent` 无法启动。
- 变更元智能体时必须运行：

```bash
python -m pytest server/tests/test_meta_agent.py -q
```

## 9. MCP 开发规则

MCP 原生集成属于后端进程管理和工具执行能力，开发时必须：

- 后端代码放在 `server/mcp/` 包内。
- 使用官方 `mcp` Python SDK 的 `ClientSession` 抽象。
- MCP Server 工作目录限制在 `server/mcp/sandboxes/`。
- 校验 `server_command`，禁止 shell 拼接和特殊字符注入。
- 连接必须有超时、断开、重试和清理逻辑。
- 前端从 `client/src/data/mcpProjects.ts` 读取命令，不硬编码命令。
- MCP 一键安装依赖容器内 `npm` / `npx`。服务端 Dockerfile 通过 Node runtime stage 提供这些命令，不应使用 Debian `apt install npm` 的长依赖链。

## 10. Xpert 发布、Goal 与 Handoff 规则

可发布 Xpert 是当前智能体主路径。修改 `server/xperts/`、Xpert Studio、HandoffExecutor 或 GoalCoordinator 时必须遵守：

- 草稿修改不得改变已发布版本；发布版本是不可变 workflow 快照。
- Xpert Chat 和自动 Handoff 必须复用 classic workflow runner，不通过服务自身 HTTP 回环调用。
- 自动 Handoff 只领取显式 `xpert:<slug-or-id>` 目标；普通 Agent 名称继续由人工 Inbox 处理。
- Planner 与目标 Xpert 在 Goal/Handoff 启动时固定发布版本，重试不得静默切换版本。
- 暂停只阻止新任务派发；取消不承诺强杀正在运行的模型请求，迟到结果只能进入审计。
- 文件型 Store 必须使用进程内锁和原子临时文件替换；测试默认使用临时目录。
- 修改该链路至少运行 Xpert Store、HandoffExecutor、Goal、RunRegistry 与对应前端构建测试。

## 11. 文件、记忆与 Knowledge Pipeline 规则

- 会话附件只能在用户显式选择时注入 Xpert、共享给 Goal 或提升到知识流水线。
- 跨 Xpert 的 conversation memory 不得隐式共享；模型提出的长期记忆必须先生成候选并由用户批准。
- API、SSE、checkpoint 和日志不得暴露本地绝对路径、附件全文、完整 prompt、embedding、vector namespace 或密钥。
- Knowledge Pipeline Job 必须固定 draft version 和源快照，按 `load/vision/process/chunk/embed/store` 顺序更新持久化 stage 状态；视觉未启用时 `vision` 必须安全跳过。
- Knowledge Pipeline Graph 只允许编译为现有 Draft，不得直接写向量/FTS5 索引或创建第二套 executor。Job 必须同时固定 `graph_revision` 与 `draft_version`。
- Graph 保存使用乐观 revision；非法 DAG、错误端口、缺失阶段、双分块器、孤立启用节点或过期 revision 不得修改 Draft。旧 Draft 表单更新图配置时必须保留节点坐标。
- Graph 节点预览不得写 Draft、Job、索引或版本，最多返回 20 条截断摘要。Embedding、双索引和检索预览只能返回安全能力/profile；图像预览不得返回原图、Base64 或完整 OCR 正文。
- 图片与扫描 PDF 必须标记为 `pipeline_required`，不得进入 legacy 即时索引。上传必须校验扩展名、声明 MIME、真实格式、10MB 文件限制、损坏文件和 40MP 解压像素上限。
- `image_understanding` 只能作为 `data_source -> image_understanding -> structured_processor` 的可选阶段；启用时必须显式固定视觉模型，并通过 PDFium/Pillow 与网关能力预检。
- 视觉模型输出必须使用严格 JSON 契约并转换为统一 DocumentBlock。逐页缓存必须绑定 source hash、视觉模型和配置 hash；重试只复用成功页，失败页必须重跑。
- 视觉 `strict` 策略任一选中页失败都阻止候选 ready；`continue_on_error` 仅在仍有可索引内容时允许带 warning 继续。checkpoint 只记录来源 ID、页码、状态、耗时和安全错误摘要。
- Processor 必须先产出稳定 `ProcessedDocument / DocumentBlock`。标题、段落、列表、表格、代码块和 PDF 页码不得在分块前退化为无结构字符串；表格和代码块清洗不得破坏内容。
- `general / qa / summary` 模式、模型 ID、生成上限、清洗选项和失败策略必须固定进候选版本 `processor_profile`。QA 索引问题并返回答案与来源，Summary 索引摘要并返回对应原文。
- 逐文档处理状态与产物必须持久化。重试只重跑 source hash 和 processor profile 未命中的失败文档，但 vector/FTS5 索引必须始终从完整成功产物重新原子构建。
- `continue_on_error` 仅在至少一个文档成功时允许生成带 warning 的候选；`strict` 任一文档失败都必须阻断 ready；所有文档失败不得产生版本。
- Processor preview 不得写草稿、Job 或索引，只能返回最多 20 个截断结构块/生成项。生成请求、preview、Job API 和 checkpoint 不得暴露正文全集、问答全文、prompt、路径或密钥。
- 候选索引不得自动上线。必须支持隔离预览、人工激活和历史版本回滚。
- Advanced RAG V2 的向量与 FTS5 索引必须同生共灭；任一索引构建或计数校验失败，必须清理两个候选 namespace，且不得生成 ready 版本。
- 分块、Embedding、检索模式、权重、Top-K、阈值和 Rerank 必须固定在候选版本 profile；预览覆盖不得静默修改版本配置。
- 父子分段只索引子段，返回父段上下文时必须保留命中子段、字符偏移和 CitationAnchor，避免引用漂移。
- Rerank 外部调用必须有超时、严格响应校验和 fail-open；降级只返回 warning，不得记录完整问题、文档正文、工具输出或密钥。
- 旧索引不得静默迁移。没有 V2 active version 时继续使用 vector-only legacy 路径，并在能力/诊断信息中明确降级状态。
- 失败、取消或重启恢复不得改变 active version；失败/取消必须清理未完成 candidate namespace。
- 普通 RAG、Chat RAG、`knowledge_retrieval` 与 `knowledge_citation` 统一读取 active version；未激活版本的旧知识库保持 legacy index 兼容。
- Xpert 与本地 Dify 只用于核对领域维度和异常行为；不得复制 AGPL 或许可证不明实现。GraphRAG 在 Processor、检索评估和知识画布稳定前保持暂缓。
- 修改知识流水线必须运行 `test_rag_pipeline_graph.py`、`test_rag_processor.py`、`test_rag_pipeline.py`、`test_rag_pipeline_execute.py`、`test_rag_retrieval_v2.py`、`test_rag_vision.py`、RAG integration 和 workflow citation 回归，并重建 Docker 做 Graph revision、视觉节点预览、逐页恢复、Processor、双索引、混合检索、Rerank 与版本切换验收。

## 12. 持久化与工作区隔离

- `server/xperts/storage/`、`server/xpert_runtime/storage/`、`server/rag/storage/`、`pipeline_processed/` 与上传目录是运行数据，不得提交。
- 影响文件型 Store 时必须覆盖进程重载、原子写入、损坏/缺失数据降级和并发更新边界。
- 当前主工作区有无关脏改动时，优先创建独立 `codex/` worktree/branch；不得把 APK、根级临时 package 文件、`.env` 或其他轮次改动混入提交。
- Docker 重建前先确认 compose 挂载覆盖 Xpert、Runtime 与 RAG 持久化目录；重启后执行恢复验收。

## 13. Xpert App/API 高风险规则

- App 必须固定不可变 `XpertVersion`；客户端不得指定模型、替换 workflow 或绕过部署版本。
- 分享 token 和 API key 只允许显示一次，服务端只能保存哈希、前缀、状态和脱敏用量。
- URL 分享凭据必须放在 fragment，前端读取后立即从地址栏移除；日志、checkpoint 和错误响应不得记录原始凭据。
- App 工具与 Handoff 默认关闭。工具开启时必须存在并先执行 `tool_policy`；策略未加载时默认拒绝。
- 公开 SSE 只输出最终回答，不转发节点变量、工具结果、内部 trace 或完整 checkpoint。
- App 不开放附件上传，不生成记忆候选；管理 API 外网部署时必须由反向代理保护。
- 修改 App/API 必须运行 `test_xpert_app_api.py`、Xpert publish、Toolset、Memory、Goal、Handoff、RunRegistry 回归和前端构建。
- Docker 验收至少覆盖 JSON/SSE、token 轮换、key 撤销、配额、版本切换、回滚和重启持久化。

## 14. Git 规范

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

## 15. 交付格式

最终回复应包含：

- 改动摘要
- 文件列表
- 验证命令与结果
- 未完成项或阻塞
- 风险和回退建议
