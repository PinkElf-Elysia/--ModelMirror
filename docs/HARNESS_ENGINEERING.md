# Harness Engineering 开发规范

Harness Engineering 是模镜的工程治理方法：在功能开发前先建立护栏，让每次变更都可理解、可测试、可回滚。

最后更新日期：2026-06-16  
维护人：模镜团队

## 1. 为什么需要 Harness

模镜经历过一次 P0 级回退。根因不是单个 bug，而是缺少版本基线、缺少测试护栏、实验功能直接替换稳定入口。因此后续所有开发都必须先建立 harness。

Harness 包括：

- 明确边界。
- 类型和接口契约。
- 最小可运行测试。
- 安全默认值。
- 运行手册和回退路径。
- 文档化上下文。

## 2. Harness Checklist

每个任务开工前回答：

| 问题 | 必填 |
| --- | --- |
| 这次改动影响哪些路由或 API？ | 是 |
| 是否触碰稳定入口 `/workflow`、`/rag`、`/api/chat`？ | 是 |
| 最小验收命令是什么？ | 是 |
| 失败如何回退？ | 是 |
| 是否新增依赖？ | 是 |
| 是否涉及密钥、子进程、文件系统或网络？ | 是 |
| 是否需要更新文档？ | 是 |

## 3. 变更分级

### Level 0 - 文档或样式

风险低。仍需确认构建不破坏。

验收：

```bash
cd client
npm.cmd run build
```

### Level 1 - 前端功能

涉及页面、组件、状态或 API 调用。

验收：

- 前端 build。
- 至少一个本地页面访问验证。
- 错误态和加载态可见。

### Level 2 - 后端 API

涉及 FastAPI、Pydantic、外部 API 或流式响应。

验收：

- `python -m py_compile ...`
- curl 样例。
- 错误路径样例。
- 不泄露密钥。

### Level 3 - 子进程 / MCP / 工作流 / RAG

风险最高。必须有隔离目录、超时、清理、测试替身和文档。

验收：

- 单元测试或集成测试。
- 失败命令不会挂死进程。
- 并发限制或限流。
- 明确回退路径。

## 4. 稳定入口保护

以下入口受保护：

| 入口 | 稳定实现 | 规则 |
| --- | --- | --- |
| `/workflow` | Dify iframe | 不得直接替换为自研版本。 |
| `/rag` | Dify iframe | 不得直接替换为自研版本。 |
| `/api/chat` | OpenRouter 代理 | 不得改坏流式协议和多模态格式。 |
| `/models` | 模型招聘会 | 不得破坏筛选和聊天入口。 |
| `/agents` | AI 人才市场 | 不得破坏智能体面试入口。 |

实验功能必须使用新路由或 feature flag。

## 5. 依赖管理

新增依赖必须说明：

- 为什么需要。
- 是否有更轻替代方案。
- 是否影响现有依赖版本。
- 安装后运行 `pip check` 或前端 build。

Python 依赖写入 `server/requirements.txt`。注意 FastAPI 和 Starlette 版本兼容。

## 6. 子进程安全

任何启动外部进程的代码必须：

- 不使用 `shell=True`。
- 命令参数是 `list[str]`。
- 拒绝 `;`、`&&`、`|`、重定向等 shell 特殊字符。
- 设置 cwd 到受控目录。
- 设置超时。
- 退出时清理进程。
- 返回简要错误，不暴露本机路径和密钥。

## 7. API Harness

新增 API 必须包含：

- Pydantic request model。
- 明确 response schema。
- 输入校验。
- 错误码策略。
- curl 示例。
- 文档更新。

## 8. 前端 Harness

新增交互组件必须包含：

- loading 状态。
- error 状态。
- empty 状态。
- disabled 状态。
- 移动端布局。
- API 失败提示。

动态表单必须有 schema fallback，不认识的字段不能让页面崩溃。

## 9. 文档 Harness

每个新模块至少包含：

- 设计背景。
- 文件位置。
- 数据流。
- API 示例。
- 测试方式。
- 常见问题。

## 10. 回退模板

每个高风险 PR 在描述中写：

```markdown
## 回退方案

1. 回滚提交 `<commit>`。
2. 确认 `/api/health` 正常。
3. 确认 `/models`、`/workflow`、`/rag` 可访问。
4. 如涉及依赖，恢复 lockfile。
```

