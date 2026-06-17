# AGENTS.md - 模镜协作与 Harness Engineering 规则

本文件是模镜仓库内 AI Agent、人类开发者和自动化任务的项目级操作说明。任何代码生成、重构、测试、提交和发布都必须优先遵守本文档。

最后更新日期：2026-06-17  
维护人：模镜团队

## 1. 项目边界

模镜 ModelMirror 是 AI 资源浏览与协作平台，当前稳定基线包含：

- 前端：React + TypeScript + Tailwind CSS + Vite。
- 后端：FastAPI + httpx + Pydantic。
- 工作流与 RAG：通过 Dify iframe + 后端代理稳定集成。
- 聊天：通过后端代理调用 OpenRouter 兼容 Chat Completions。
- 资源页：模型、智能体、MCP、Skill、提示词、专家团。

稳定入口：

- `/models`
- `/agents`
- `/chat/:modelId`
- `/workflow` - Dify 稳定工作流
- `/rag` - Dify 稳定资料库
- `/mcps`
- `/skills`

## 2. Harness Engineering 原则

Harness Engineering 的意思是：先搭护栏，再做功能。任何变更都必须有明确范围、验证方式、回退路径和可观测结果。

### 强制原则

1. 小步交付：一次只改一个可验证目标。
2. 稳定路径优先：实验功能不得替换稳定主入口。
3. 先读代码：实现前必须确认真实文件、接口和数据结构。
4. 先定义验收：每个任务必须有可运行的 acceptance check。
5. 可回退：影响主路径的变更必须写明回退方案。
6. 不泄密：不得提交 `.env`、API Key、token、日志中的敏感信息。
7. 不破坏：不得重置、删除或回滚用户未授权的文件。

## 3. 红线

严禁：

- 无设计文档直接重写工作流引擎或 RAG 管道。
- 未测试通过就替换 `/workflow` 或 `/rag`。
- 将真实 `OPENROUTER_API_KEY`、`DIFY_API_KEY`、GitHub token 写入仓库。
- 在前端代码中硬编码后端密钥。
- 使用不安全批量替换处理中文源码。
- 直接提交 `node_modules/`、`client/dist/`、日志、临时抓取目录。
- 为了“快速修复”禁用安全检查、类型检查或输入校验。

## 4. 推荐工作流

每次任务按以下顺序推进：

1. Inspect - 读取相关文件、路由、接口和测试。
2. Plan - 列出变更范围和验收命令。
3. Implement - 小步修改，避免无关重构。
4. Verify - 运行最小必要检查。
5. Document - 更新相关文档。
6. Commit - 使用清晰提交信息。

## 5. 验证命令

前端：

```bash
cd client
npm.cmd run build
```

后端语法：

```bash
python -m py_compile server/main.py server/api/dify_proxy.py
```

workflow-native 语法与测试：

```bash
python -m py_compile server/main.py server/api/workflow_native.py server/workflow_native/schemas.py server/workflow_native/validate.py
python -m pytest server/tests/test_workflow_native_validate.py -q
```

RAG 回归：

```bash
python -m pytest server/tests/test_rag.py -q
```

健康检查：

```bash
curl http://localhost:8000/api/health
curl http://localhost:8000/api/dify/health
```

链接检查可使用项目内 Python 脚本或临时命令，但不得提交临时脚本，除非它成为正式工具。

## 6. Git 规范

分支：

```text
feature/<short-topic>
fix/<short-topic>
docs/<short-topic>
chore/<short-topic>
```

提交：

```text
type: 简短中文说明
```

示例：

```text
docs: 添加 harness 工程规范
fix: 修复 MCP 工具调用错误处理
feature: 添加 MCP stdio 客户端管理器
```

提交前必须确认：

```bash
git status --short
git diff --cached --name-only
```

## 7. Dify 与自研工作流规则

当前 `/workflow` 与 `/rag` 必须保持 Dify 稳定集成。

任何自研替代必须：

- 放在独立路由，例如 `/workflow-native`。
- 有设计文档。
- 有后端单元测试。
- 能和 Dify 稳定版并行运行。
- 失败时能一键回退到 Dify。

参考：

- [docs/postmortem-workflow-rewrite.md](docs/postmortem-workflow-rewrite.md)
- [docs/retry-plan-workflow-native.md](docs/retry-plan-workflow-native.md)
- [docs/workflow-native-design.md](docs/workflow-native-design.md)

### workflow-native 增量规则

workflow-native 是实验线，不是稳定主入口。任何新增节点、运行器分支或校验规则必须遵守：

- 前端节点类型、后端 `NativeNodeKind`、validate 规则、测试用例和文档必须同步更新。
- `/api/workflow-native/validate` 只做静态校验，不调用模型、RAG、MCP 或外部 HTTP。
- classic `/api/workflow/run` 可以试点本地节点执行，但不得影响 `/workflow` Dify iframe。
- 涉及外部请求、文件读取、模型调用的节点必须有默认关闭或安全降级路径。
- 涉及人工介入、暂停、恢复的节点必须提供 TTL、状态查询和显式 resume 接口；MVP 阶段只允许内存态，不得伪造持久化审批能力。
- 每新增一类节点至少补一条合法样例和一条非法样例测试。
- 失败时回退方式优先隐藏 `/workflow-native` 入口或将新节点运行分支降级为 no-op，不回滚稳定 Dify 路径。

## 8. MCP 开发规则

MCP 原生集成属于后端进程管理和工具执行能力，风险较高。开发时必须：

- 将后端代码放在 `server/mcp/` 包内。
- 使用官方 `mcp` Python SDK 的 `ClientSession` 抽象。
- MCP Server 工作目录限制在 `server/mcp/sandboxes/`。
- 校验 `server_command`，禁止 shell 拼接和特殊字符注入。
- 连接有超时、断开、重试和清理逻辑。
- REST API 仅暴露受控 session 操作。
- 前端从 `client/src/data/mcpProjects.ts` 读取命令，不硬编码命令。

## 9. 文档要求

新增或修改功能时同步更新：

- `docs/README.md`
- 对应模块文档，例如 `docs/BACKEND.md`、`docs/FRONTEND.md`
- 新术语需更新 `docs/GLOSSARY.md`

文档必须：

- 简体中文。
- 代码块标注语言。
- 与当前代码一致，不写虚构接口。
- 尾部包含最后更新日期和维护人。

## 10. 交付格式

最终回复应包含：

- 改动摘要。
- 文件列表。
- 验证命令与结果。
- 未完成项或阻塞。
- 风险和回退建议。
