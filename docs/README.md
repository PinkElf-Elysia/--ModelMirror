# 模镜项目文档中心

这里是模镜 ModelMirror 的工程文档入口。文档目标是让新成员、产品设计同学以及其他大模型在不依赖聊天上下文的情况下理解项目结构、运行方式和关键约束。

## 文档目录

| 文档 | 简介 |
| --- | --- |
| [ARCHITECTURE.md](./ARCHITECTURE.md) | 项目愿景、系统架构、路由模块和主要数据流。 |
| [QUICK_START.md](./QUICK_START.md) | 5 分钟本地启动前端、后端和可选 Dify。 |
| [FRONTEND.md](./FRONTEND.md) | React 前端目录、路由、组件、状态和开发规范。 |
| [BACKEND.md](./BACKEND.md) | FastAPI 后端接口、流式响应、环境变量和扩展方式。 |
| [DATABASE.md](./DATABASE.md) | 当前静态数据、本地状态和未来数据库迁移方案。 |
| [DEPLOYMENT.md](./DEPLOYMENT.md) | 开发、生产、Docker、日志和运维建议。 |
| [INTEGRATION_DIFY.md](./INTEGRATION_DIFY.md) | Dify iframe + 后端代理集成方案与排障。 |
| [THEME.md](./THEME.md) | “AI 牛马招聘会”主题、设计 token 和 UI 规范。 |
| [GLOSSARY.md](./GLOSSARY.md) | 项目常用术语、缩写和内部黑话。 |
| [ONBOARDING.md](./ONBOARDING.md) | 新成员第一天到第一周的上手路线。 |
| [HARNESS_ENGINEERING.md](./HARNESS_ENGINEERING.md) | 开发护栏、验收标准、回退策略和高风险变更规则。 |
| [postmortem-workflow-rewrite.md](./postmortem-workflow-rewrite.md) | 自研工作流失败复盘。 |
| [retry-plan-workflow-native.md](./retry-plan-workflow-native.md) | 未来重试自研工作流的阶段路线。 |

## 按角色推荐阅读路径

### 前端工程师

1. [QUICK_START.md](./QUICK_START.md)
2. [FRONTEND.md](./FRONTEND.md)
3. [THEME.md](./THEME.md)
4. [HARNESS_ENGINEERING.md](./HARNESS_ENGINEERING.md)
5. [INTEGRATION_DIFY.md](./INTEGRATION_DIFY.md)

### 后端工程师

1. [QUICK_START.md](./QUICK_START.md)
2. [BACKEND.md](./BACKEND.md)
3. [HARNESS_ENGINEERING.md](./HARNESS_ENGINEERING.md)
4. [INTEGRATION_DIFY.md](./INTEGRATION_DIFY.md)
5. [DEPLOYMENT.md](./DEPLOYMENT.md)

### 产品经理

1. [ARCHITECTURE.md](./ARCHITECTURE.md)
2. [GLOSSARY.md](./GLOSSARY.md)
3. [ONBOARDING.md](./ONBOARDING.md)

### 设计师

1. [ARCHITECTURE.md](./ARCHITECTURE.md)
2. [THEME.md](./THEME.md)
3. [FRONTEND.md](./FRONTEND.md)

## 如何贡献文档

- 修改文档前先确认对应代码是否已经变化，不要写“未来可能”冒充当前能力。
- 所有文档使用简体中文，API、SDK、MCP、RAG 等技术名词保留英文。
- 命令必须放在带语言标识的代码块中，例如 `bash`、`json`、`typescript`。
- 文档之间使用相对链接。
- 新增功能时同步更新 README、对应模块文档和术语表。

最后更新日期：2026-06-10  
维护人：模镜团队
