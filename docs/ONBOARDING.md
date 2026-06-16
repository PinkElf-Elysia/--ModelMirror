# 新成员入职指引

欢迎加入模镜。这个项目经历过一次工作流自研失败和大规模回退，因此我们非常重视版本控制、文档和渐进式交付。

## 项目使命

模镜要成为 AI 时代的一站式资源浏览器：帮助用户发现模型、智能体、MCP、Skill、提示词，并把这些资源组合成可运行的聊天、工作流和知识库应用。

## 第一天任务清单

- [ ] 获取 GitHub 私密仓库访问权限。
- [ ] 克隆仓库并按 [QUICK_START.md](./QUICK_START.md) 启动项目。
- [ ] 打开 `/models`、`/agents`、`/chat/:modelId`、`/workflow`、`/rag` 了解产品。
- [ ] 阅读 [ARCHITECTURE.md](./ARCHITECTURE.md)。
- [ ] 阅读 [HARNESS_ENGINEERING.md](./HARNESS_ENGINEERING.md)，理解开发护栏和回退要求。
- [ ] 阅读与你角色相关的文档：
  - 前端：[FRONTEND.md](./FRONTEND.md)
  - 后端：[BACKEND.md](./BACKEND.md)
  - 设计：[THEME.md](./THEME.md)
- [ ] 阅读 [postmortem-workflow-rewrite.md](./postmortem-workflow-rewrite.md)，理解为什么禁止无设计的大重构。
- [ ] 加入团队通讯工具：待补充。

## 开发环境配置

必备：

- Node.js 18+
- Python 3.11+
- Git

可选：

- Docker / Docker Compose
- Dify 社区版本地服务

验证命令：

```bash
cd client
npm run build
```

```bash
cd ..
python -m py_compile server/main.py server/api/dify_proxy.py
```

## 分支与提交规范

分支命名：

```text
feature/<short-description>
fix/<short-description>
docs/<short-description>
chore/<short-description>
```

提交信息：

```text
type: 简短中文说明
```

示例：

```text
docs: 添加后端 API 文档
fix: 修复聊天流式错误提示
feature: 添加 MCP 项目卡片
```

## PR 流程

1. 从最新 `main` 创建分支。
2. 小步提交，避免一个 PR 混入多个主题。
3. 提交前运行构建和必要检查。
4. PR 描述必须包含：
   - 改了什么
   - 为什么改
   - 如何验证
   - 风险和回滚方式
5. 至少一名成员 Review 后合并。

## 测试规范

当前测试体系仍在建设中，最低要求：

- 前端：`npm run build`
- 后端：`python -m py_compile server/main.py server/api/dify_proxy.py`
- 关键接口：`/api/health`、`/api/dify/health`
- 核心页面：`/models`、`/agents`、`/workflow`、`/rag`

新增后端执行器、解析器、路由匹配等核心逻辑时，必须补单元测试。

## 工程红线

- 不允许把 API Key 写入前端或提交到 Git。
- 不允许未验证实验功能替换 `/workflow` 和 `/rag` 主入口。
- 不允许无设计文档的大规模重构。
- 不允许构建失败时交付。
- 不允许通过不安全批量替换处理中文源码。

## 重要联系人

| 角色 | 姓名 | 联系方式 |
| --- | --- | --- |
| 产品负责人 | 待补充 | 待补充 |
| 前端负责人 | 待补充 | 待补充 |
| 后端负责人 | 待补充 | 待补充 |
| 运维负责人 | 待补充 | 待补充 |

最后更新日期：2026-06-10  
维护人：模镜团队
