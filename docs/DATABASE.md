# 数据模型与存储方案

## 当前存储方式

模镜当前没有自建数据库。数据分为四类：

| 类型 | 存储位置 | 说明 |
| --- | --- | --- |
| 模型数据 | `client/src/data/models.ts` | 静态模型目录，含价格、能力、筛选字段。 |
| 智能体数据 | `client/src/data/agents.ts`、`server/data/agents.json` | 前端展示和后端自动路由/团队协作各有一份数据。 |
| MCP / Skill 数据 | `client/src/data/mcpProjects.ts`、`client/src/data/skillProjects.ts` | 首批真实项目卡片数据。 |
| 提示词数据 | `client/src/data/promptLibrary.json` | 提示词助手使用的分类与内容。 |
| 用户偏好 | `localStorage` | 偏好模型、高级参数、部分会话状态。 |
| 工作流与 RAG | Dify 内部数据库 | 稳定主路径由 Dify 社区版管理。 |
| 经典工作流草稿 | `localStorage` | `/workflow/classic` 实验入口使用。 |

## 模型数据接口

`client/src/data/models.ts` 中的 `Model` 包含：

```typescript
interface Model {
  id: string;
  name: string;
  description: string;
  context_length: number;
  pricing: { input: number; output: number };
  price_cny: { input: number; output: number };
  input_modalities: string[];
  categories: string[];
  supported_parameters: string[];
  series: string;
  tags: string[];
  provider: string;
  model_author: string;
  distillable: boolean;
  zero_data_retention: boolean;
  in_region_routing: boolean;
  active: boolean;
}
```

用途：

- `/models` 卡片展示。
- 模型筛选。
- 聊天页模型选择器。
- 多模态能力判断。

## 智能体数据接口

前端 `agents.ts` 用于人才市场卡片；后端 `agents.json` 用于路由和团队协作。核心字段：

```typescript
interface AgentRecord {
  id: string;
  name: string;
  department: string;
  expertise: string;
  scenarios: string;
  prompt: string;
  sourceUrl?: string;
  emoji?: string;
  popularity?: number;
}
```

## MCP 项目数据

```typescript
interface ResourceProject {
  id: string;
  name: string;
  description: string;
  repository: string;
  stars: string;
  language: string;
  updatedAt: string;
  installCommand: string;
  tags: string[];
}
```

实际字段以 `ResourceProjectCard` 消费的数据为准。新增 MCP 时应优先补充真实仓库、安装命令和简短中文描述。

## Skill 项目数据

Skill 数据与 MCP 类似，展示为“技能货架”。对于综合仓库，例如 `anthropics/skills`，可以拆成多个子技能卡片，但必须注明来源仓库。

## localStorage Key

| Key | 用途 |
| --- | --- |
| `modelmirror-preferred-model-id` | 用户偏好的默认聊天模型。 |
| 聊天高级参数相关 key | 按模型记忆 temperature、top_p、max_tokens 等。 |
| 经典工作流草稿 key | `/workflow/classic` 保存实验画布。 |

## Dify 数据层

Dify 社区版通常包含：

- PostgreSQL：应用、工作流、知识库、文档元数据。
- Redis / Queue：异步任务与缓存。
- 向量数据库或 Dify 内置索引配置：知识库检索。
- 文件存储：上传文档和解析结果。

模镜不直接访问这些数据库，而是通过 Dify Web iframe 和 `/api/dify/*` 代理访问 Dify API。

## 未来数据库迁移方案

当需要自建用户体系和资源收藏时，建议引入 PostgreSQL：

```text
users
resources
favorites
chat_sessions
chat_messages
workflow_drafts
agent_teams
```

推荐技术路线：

- PostgreSQL 作为主库。
- Prisma 或 SQLModel 管理 schema。
- Redis 用于限流、任务队列和短期缓存。
- 静态资源数据逐步迁移到管理后台或同步任务。

## 数据更新原则

- 不要手动改生产密钥或用户数据。
- 大型静态数据更新必须单独提交，避免和 UI 改动混在一起。
- 模型价格、MCP stars、Skill 仓库信息应注明更新时间。
- 如果数据来自外部仓库，保留来源链接。

最后更新日期：2026-06-10  
维护人：模镜团队
