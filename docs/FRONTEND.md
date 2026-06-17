# 前端架构与开发指南

最后更新日期：2026-06-17
维护人：模镜团队

## 技术栈

- React 19
- TypeScript
- Tailwind CSS
- Vite
- React Router
- ReactMarkdown + remark-gfm
- @xyflow/react

## 目录结构

```text
client/
├── src/
│   ├── App.tsx                  # 路由配置
│   ├── main.tsx                 # React 入口
│   ├── components/              # 通用组件
│   ├── components/workflow/     # 经典自研工作流画布
│   ├── context/                 # React Context
│   ├── data/                    # 静态资源数据
│   ├── pages/                   # 路由页面
│   ├── theme/                   # 主题与资源导航
│   ├── types/                   # TypeScript 类型
│   └── utils/                   # SSE、图片处理、压缩等工具
├── tailwind.config.js
└── vite.config.ts
```

## 路由

| 路径 | 页面组件 | 说明 |
| --- | --- | --- |
| `/` | `Navigate` | 重定向到 `/models`。 |
| `/models` | `ModelListPage` | 模型招聘会。 |
| `/agents` | `AgentsPage` | AI 人才市场。 |
| `/expert-team` | `ExpertTeamPage` | 专家团。 |
| `/mcps` | `McpBrowserPage` | MCP 工具。 |
| `/skills` | `SkillBrowserPage` | Skill 技能。 |
| `/prompts` | `ComingSoonPage` | 提示词市场占位。 |
| `/chat/:modelId` | `ChatPage` | 面试间。 |
| `/workflow` | `WorkflowClassicPage` | 经典自研 React Flow 工作流。 |
| `/workflow/:id` | `WorkflowClassicPage` | 工作流草稿入口。 |
| `/workflow/classic` | `WorkflowClassicPage` | 兼容旧入口。 |
| `/workflow-native` | `WorkflowNativePage` | workflow-native 实验入口。 |
| `/rag` | `RagPage` | 本地 RAG 资料库。 |
| `/settings` | `SystemSettingsPage` | newAPI 控制台 iframe。 |
| `/studio` | `StudioHomePage` | 工作台总览。 |

## 聊天图片输出链路

图片生成模型的输出路径由以下文件协作完成：

| 文件 | 职责 |
| --- | --- |
| `utils/fetchChatStream.ts` | 读取 SSE，解析 `content`、`delta.images`、`message.images`，把 `image_url.url` 转成 `![图片](URL)`。 |
| `utils/extractImages.ts` | 从消息文本中提取 markdown 图片、内联 SVG、data URL、裸图片 URL，生成图片卡片数据。 |
| `pages/ChatPage.tsx` | 渲染用户上传图片和模型输出图片；点击图片进入 Lightbox，支持保存原图和 SVG 转 PNG。 |

开发约束：

- 不改变 `onDelta(text: string)` 签名。
- 不破坏纯文本模型的流式追加。
- 不破坏用户上传图片的 `message.images` 展示。
- `data:image/...` 必须可显示为图片卡片，不能只留在 Markdown 文本里。
- Lightbox 统一处理上传图、模型输出 URL、data URL 和 SVG。

## 验证

```bash
cd client
npm.cmd run build
```

手动验收：

1. 打开 `/chat/recraft%2Frecraft-v3`。
2. 输入“画一只猫”。
3. Assistant 消息中应出现至少一张图片卡片。
4. 点击图片应进入 Lightbox。
5. 纯文本模型仍应逐字/逐段流式显示文本。

## 开发规范

- 组件文件使用 PascalCase。
- 类型尽量靠近数据源或放入 `types/`。
- 不新增 UI 组件库，优先使用 Tailwind 和现有组件。
- 中文文案必须以 UTF-8 写入，避免 PowerShell 编码导致 mojibake。
- 不在前端保存 API Key。
