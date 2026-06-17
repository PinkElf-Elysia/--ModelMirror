# 模镜项目文档中心

这里是 ModelMirror 的工程文档入口。文档目标是让新成员、人类开发者和其他大模型在不依赖聊天上下文的情况下理解项目结构、运行方式和关键约束。

最后更新日期：2026-06-17
维护人：模镜团队

## 文档目录

| 文档 | 简介 |
| --- | --- |
| [ARCHITECTURE.md](./ARCHITECTURE.md) | 项目愿景、系统架构、路由模块和主要数据流。 |
| [QUICK_START.md](./QUICK_START.md) | 5 分钟本地启动前端、后端和 Docker Compose。 |
| [FRONTEND.md](./FRONTEND.md) | React 前端目录、路由、组件、聊天图片输出和开发规范。 |
| [BACKEND.md](./BACKEND.md) | FastAPI 后端接口、SSE、newAPI 网关、图片生成输出和环境变量。 |
| [DATABASE.md](./DATABASE.md) | 当前静态数据、本地状态、RAG 存储和未来数据库迁移方案。 |
| [DEPLOYMENT.md](./DEPLOYMENT.md) | 开发、生产、Docker、日志和运维建议。 |
| [MCP_INTEGRATION.md](./MCP_INTEGRATION.md) | MCP stdio 集成、REST API、前端交互和测试指南。 |
| [RAG_INTEGRATION.md](./RAG_INTEGRATION.md) | 本地 RAG 资料库、文档上传、向量检索、聊天引用和测试指南。 |
| [SKILL_INTEGRATION.md](./SKILL_INTEGRATION.md) | Skill 扩展包安装、管理、聊天注入和测试指南。 |
| [workflow-native-design.md](./workflow-native-design.md) | 自研工作流 native 实验线的设计、API 契约和回退方案。 |
| [THEME.md](./THEME.md) | “AI 牛马招聘会”主题、设计 token 和 UI 规范。 |
| [GLOSSARY.md](./GLOSSARY.md) | 项目常用术语、缩写和内部黑话。 |
| [HARNESS_ENGINEERING.md](./HARNESS_ENGINEERING.md) | 开发护栏、验收标准、回退策略和高风险变更规则。 |
| [postmortem-workflow-rewrite.md](./postmortem-workflow-rewrite.md) | 自研工作流失败复盘。 |
| [retry-plan-workflow-native.md](./retry-plan-workflow-native.md) | 未来重试自研工作流的阶段路线。 |

## 按角色推荐阅读路径

前端工程师：

1. [QUICK_START.md](./QUICK_START.md)
2. [FRONTEND.md](./FRONTEND.md)
3. [THEME.md](./THEME.md)
4. [HARNESS_ENGINEERING.md](./HARNESS_ENGINEERING.md)

后端工程师：

1. [QUICK_START.md](./QUICK_START.md)
2. [BACKEND.md](./BACKEND.md)
3. [HARNESS_ENGINEERING.md](./HARNESS_ENGINEERING.md)
4. [MCP_INTEGRATION.md](./MCP_INTEGRATION.md)
5. [RAG_INTEGRATION.md](./RAG_INTEGRATION.md)

产品和设计：

1. [ARCHITECTURE.md](./ARCHITECTURE.md)
2. [THEME.md](./THEME.md)
3. [GLOSSARY.md](./GLOSSARY.md)

AI Agent：

1. [../AGENTS.md](../AGENTS.md)
2. [HARNESS_ENGINEERING.md](./HARNESS_ENGINEERING.md)
3. 与任务相关的模块文档

## 如何贡献文档

- 修改文档前先确认对应代码是否已经变化，不写虚构接口。
- 所有文档使用简体中文，API、SDK、MCP、SSE 等技术名词保留英文。
- 命令必须放在带语言标识的代码块中，例如 `bash`、`json`、`typescript`。
- 文档之间使用相对链接。
- 新增功能时同步更新根 README、模块文档、术语表和 harness。
