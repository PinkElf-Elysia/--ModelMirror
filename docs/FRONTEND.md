# 前端架构与开发指南

## 技术栈

- React 19
- TypeScript
- Tailwind CSS
- Vite
- React Router v6
- React Markdown + remark-gfm
- React Flow（`@xyflow/react`，用于 `/workflow/classic` 实验画布）

## 目录结构

```text
client/
├── src/
│   ├── App.tsx                     # 路由配置
│   ├── main.tsx                    # React 入口与 Provider
│   ├── index.css                   # Tailwind 和全局样式
│   ├── components/                 # 通用组件
│   │   ├── filters/                # 模型筛选组件
│   │   ├── workflow/               # 经典自研画布组件
│   │   └── dify/                   # Dify iframe 包装
│   ├── context/                    # React Context
│   ├── data/                       # 静态资源数据
│   ├── pages/                      # 路由页面
│   ├── theme/                      # 主题文案和资源导航配置
│   ├── types/                      # TypeScript 类型
│   └── utils/                      # SSE、图片压缩、友好文案等工具
├── tailwind.config.js
└── vite.config.ts
```

## 核心组件树

```text
main.tsx
└── BrowserRouter
    └── ModelPreferenceProvider
        └── App
            ├── PageContainer
            │   ├── ResourceNav
            │   ├── SystemCapabilityBar
            │   └── 页面内容
            ├── ModelListPage
            │   ├── FilterPanel
            │   ├── FederationRouterCard
            │   └── ModelCard
            ├── AgentsPage
            │   ├── PlatformCapabilityCard
            │   └── AgentCard
            ├── ChatPage
            │   ├── AdvancedParamsPanel
            │   └── PromptSidebar
            ├── WorkflowEditorPage
            │   └── DifyWorkspaceFrame
            └── RagPage
                └── DifyWorkspaceFrame
```

## 路由配置

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
| `/workflow` | `WorkflowEditorPage` | Dify 工作流 iframe。 |
| `/workflow/new` | `WorkflowEditorPage` | 兼容旧入口。 |
| `/workflow/:id` | `WorkflowEditorPage` | 兼容旧入口。 |
| `/workflow/classic` | `WorkflowClassicPage` | 经典自研画布。 |
| `/workflow-native` | `WorkflowNativePage` | 自研工作流 native 实验入口，提供 validate 演示；节点执行仍由 classic 运行器试点。 |
| `/workflow-native/:id` | `WorkflowNativePage` | 自研工作流 native 草稿占位入口。 |
| `/rag` | `RagPage` | Dify 知识库 iframe。 |
| `/studio` | `StudioHomePage` | 工作台总览。 |

## 状态管理

当前没有 Redux 等全局状态库。

- `ModelPreferenceContext`：保存用户偏好的默认聊天模型，写入 `localStorage`。
- 页面内部状态：使用 `useState`、`useMemo`、`useEffect`。
- 聊天参数：`AdvancedParamsPanel` 按模型 ID 记忆到 `localStorage`。
- 工作流经典画布：使用 React Flow 状态和本地草稿。

## 数据文件

| 文件 | 用途 |
| --- | --- |
| `data/models.ts` | 模型目录、价格、能力、筛选字段。 |
| `data/agents.ts` | AI 智能体角色。 |
| `data/mcpProjects.ts` | MCP 项目卡片数据。 |
| `data/skillProjects.ts` | Skill 项目卡片数据。 |
| `data/promptLibrary.json` | 提示词助手分类与提示词。 |
| `data/filterOptions.ts` | 模型筛选选项。 |
| `data/filterState.ts` | 模型筛选状态类型与默认值。 |

## 主题系统

主题 token 在 `tailwind.config.js` 中扩展：

- `hire`：招聘会暖橙色系。
- `brand`：青色品牌色。
- `accent`：紫色强调色。
- `ink` / `surface`：深色背景与卡片层级。
- 阴影：`shadow-prism`、`shadow-glow`、`shadow-dock`。
- 动画：`soft-rise`、`slow-pan`、`pulse-line`。

全局样式在 `index.css`，包含背景、滚动条、surface card/panel 等基础样式。

## 开发规范

- 组件文件使用 PascalCase，例如 `ModelCard.tsx`。
- 类型尽量靠近数据源或放入 `types/`。
- 不新增 UI 组件库；优先用 Tailwind 和现有组件。
- 真实本地文件路径和代码引用应使用绝对路径或清晰相对路径。
- 不在前端保存 API Key。
- 中文文案必须以 UTF-8 写入，避免 PowerShell GBK 导致 mojibake。
- 不允许实验功能直接替换稳定入口，工作流主入口保持 Dify 版。

## 如何新增一个资源类型页面

以新增 “Dataset Marketplace” 为例：

1. 在 `theme/resources.ts` 中新增导航项。
2. 在 `pages/` 下创建 `DatasetMarketplacePage.tsx`。
3. 在 `App.tsx` 中添加路由。
4. 如有数据，创建 `data/datasetProjects.ts`。
5. 使用 `PageContainer` 包装页面，保持服务台和移动端导航一致。
6. 更新 [ARCHITECTURE.md](./ARCHITECTURE.md) 和 [GLOSSARY.md](./GLOSSARY.md)。

## 构建命令

```bash
cd client
npm run build
```

最后更新日期：2026-06-16
维护人：模镜团队
