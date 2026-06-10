# 术语表

| 中文名称 | 英文 / 缩写 | 解释 | 在项目中的使用场景 |
| --- | --- | --- | --- |
| 模镜 | ModelMirror | 项目名称，AI 资源发现与协作平台。 | 页面标题、README、服务端应用名。 |
| 模型招聘会 | Models Job Fair | 模型浏览页的主题化表达。 | `/models`。 |
| 面试间 | Chat Room | 与模型或智能体对话的页面。 | `/chat/:modelId`。 |
| 智能体 | Agent | 带有人设、专长和系统提示词的 AI 角色。 | `/agents`、自动路由、AI Team。 |
| MCP | Model Context Protocol | 一种让模型连接外部工具和上下文的协议。 | `/mcps` 工具采购页。 |
| Skill | Agent Skill | 可复用的智能体能力包或技能说明。 | `/skills` 技能货架。 |
| RAG | Retrieval-Augmented Generation | 检索增强生成，把资料库片段作为上下文提供给模型。 | `/rag`、Dify 知识库、聊天增强。 |
| SSE | Server-Sent Events | 服务端向浏览器持续推送文本事件的协议。 | `/api/chat`、Fusion、团队协作、工作流运行。 |
| iframe | Inline Frame | 在当前页面内嵌另一个 Web 应用。 | Dify 工作流和资料库稳定入口。 |
| Dify | Dify | 开源 LLM 应用开发平台，提供工作流和知识库。 | `/workflow`、`/rag`、`/api/dify/*`。 |
| OpenRouter | OpenRouter | OpenAI 兼容模型网关。 | 后端 `/api/chat` 调用模型。 |
| Fusion | Model Fusion | 多模型并行回答后由裁判模型综合。 | `/api/fusion/chat`、专家团。 |
| AI Team | AI Team | 多个智能体串行或辩论式协作。 | `/api/team/chat`、专家团。 |
| 自动路由 | Auto Routing | 根据用户需求匹配最合适的智能体。 | `/api/route-agent`。 |
| 提示词工程 | Prompt Engineering | 设计高质量模型输入的方法。 | 提示词助手、超级提示词模式。 |
| 超级提示词模式 | Super Prompt Mode | 前端在用户消息前静默包装结构化提示词。 | `ChatPage` + `PromptSidebar`。 |
| 多模态 | Multimodal | 文本、图片、音频、视频等输入能力。 | 模型能力筛选和聊天图片上传。 |
| Vision 格式 | OpenAI Vision Content | `content` 为 text/image_url 数组的消息格式。 | `/api/chat` 多模态请求。 |
| 资料库 | Dataset / Knowledge Base | 文档集合及其分段和检索能力。 | Dify 知识库、RAG。 |
| 工作流 | Workflow | 多节点编排的 AI 流程。 | Dify 工作流、经典自研画布。 |
| 经典画布 | Classic Canvas | 早期 React Flow 自研 MVP，保留实验用途。 | `/workflow/classic`。 |
| 工牌 / 展位 | Badge / Booth | 招聘会主题中的 UI 隐喻。 | 模型卡片、智能体卡片、筛选标签。 |
| UGC | User-Generated Content | 用户生成内容。 | 未来提示词市场和自定义工作流。 |
| localStorage | localStorage | 浏览器本地键值存储。 | 偏好模型、高级参数、实验草稿。 |
| Pydantic | Pydantic | Python 数据校验库。 | 后端请求体校验。 |
| FastAPI | FastAPI | Python Web 框架。 | 后端 API 服务。 |
| Vite | Vite | 前端开发与构建工具。 | `client/`。 |
| React Flow | React Flow / XYFlow | 节点画布库。 | `/workflow/classic`。 |

最后更新日期：2026-06-10  
维护人：模镜团队
