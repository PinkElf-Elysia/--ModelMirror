# Harness Engineering 开发规范

Harness Engineering 是模镜的工程治理方法：先建立护栏，再开发功能，让每次变更都可理解、可测试、可回退。

最后更新日期：2026-07-13
维护人：模镜团队

## 1. Harness Checklist

每个任务开工前回答：

| 问题 | 必填 |
| --- | --- |
| 本次影响哪些路由或 API？ | 是 |
| 是否触碰 `/api/chat`、`/workflow`、`/rag` 等主路径？ | 是 |
| 最小验收命令是什么？ | 是 |
| 失败如何回退？ | 是 |
| 是否新增依赖？ | 是 |
| 是否涉及密钥、子进程、文件系统或网络？ | 是 |
| 是否需要更新文档？ | 是 |

## 2. 变更分级

### Level 0 - 文档或样式

验证：

```bash
cd client
npm.cmd run build
```

### Level 1 - 前端功能

验证：

- 前端 build。
- 至少一个本地页面访问验证。
- loading / error / empty / disabled 状态可见。

### Level 2 - 后端 API

验证：

```bash
python -m py_compile server/main.py
```

并补充 curl 样例、错误路径和密钥泄露检查。

### Level 3 - MCP / 工作流 / RAG / Xpert App / 图片生成链路

最高风险。必须有隔离、超时、测试替身或真实冒烟。

## 3. 主路径保护

| 入口 | 实现 | 规则 |
| --- | --- | --- |
| `/api/chat` | OpenAI 兼容 SSE 代理 | 不得破坏文本流式追加、多模态输入或图片输出。 |
| `/chat/:modelId` | ChatPage | 不得破坏用户上传图片和 Lightbox。 |
| `/workflow` | 经典自研工作流 | 不得无测试改动运行器主链路。 |
| `/workflow-native` | 实验线 | 新节点必须同步类型、校验、测试和文档。 |
| `/rag` | 本地 RAG | 不得提交上传文件、向量库或临时存储。 |
| `/settings` | newAPI iframe | 不得在前端硬编码密钥。 |
| `/apps/:appSlug` | 未列出 Xpert App | 分享 token 只经 URL fragment 与请求 header 传递。 |
| `/api/v1/xpert-apps/*/chat/completions` | OpenAI 兼容 App API | 固定部署版本，只公开最终输出，密钥只存哈希。 |

## 4. Xpert App/API Harness

App/API 属于公开边界，修改 `server/xperts/app_*`、App 页面或 classic runner 的 App 分支时必须验证：

- XpertVersion 固定，草稿和新发布版本不会静默改变线上行为。
- token/key 原值不落盘、不进入日志、checkpoint、错误响应或 Git diff。
- 工具、Handoff、记忆默认关闭；工具策略未加载时默认拒绝。
- JSON 与 SSE 均只返回最终回答，SSE 以 `[DONE]` 结束。
- 无效、过期、撤销凭据返回 401；RPM、日配额和并发超限返回 429 与 `Retry-After`。
- 停用、部署 v2、回滚 v1 和容器重启后行为符合部署记录。

最小验证：

```bash
python -m pytest server/tests/test_xpert_app_api.py -q
python -m pytest server/tests/test_xpert_publish.py server/tests/test_xpert_runtime_toolset.py -q
cd client && npm.cmd run build
```

## 5. `/api/chat` 图片输出 Harness

修改以下文件时必须运行本节验收：

- `server/main.py`
- `client/src/utils/fetchChatStream.ts`
- `client/src/utils/extractImages.ts`
- `client/src/pages/ChatPage.tsx`

必须保持：

- `onDelta(text: string)` 签名不变。
- 纯文本模型仍按文本流式追加。
- 图片生成模型输出能进入图片卡片和 Lightbox。
- `data:image/...` 不依赖 ReactMarkdown 协议白名单，必须由 `extractImages` 提取。
- 用户上传图片 `message.images` 逻辑不变。

最小验证：

```bash
cd client
npm.cmd run build
```

```bash
python -m py_compile server/main.py
```

真实图片模型冒烟：

```bash
curl -N -X POST http://localhost:8000/api/chat ^
  -H "Content-Type: application/json" ^
  -d "{\"model_id\":\"recraft/recraft-v3\",\"messages\":[{\"role\":\"user\",\"content\":\"画一只猫\"}]}"
```

预期：

- 响应包含 `image_url` 或 `data:image/...`。
- `/chat/recraft%2Frecraft-v3` 中出现至少一张可点击图片。
- 点击图片进入 Lightbox。

## 6. 文档 Harness

新增或修改功能时同步更新：

- 根 `README.md`
- `docs/README.md`
- 相关模块文档，例如 `docs/FRONTEND.md`、`docs/BACKEND.md`
- `docs/GLOSSARY.md`（新术语）
- `AGENTS.md`（新 harness 或红线）

文档必须：

- 简体中文。
- UTF-8 编码。
- 代码块标注语言。
- 与当前代码一致，不写虚构接口。
- 尾部或头部包含最后更新日期和维护人。

## 7. 回退模板

高风险 PR 描述中写明：

```markdown
## 回退方案

1. 回滚提交 `<commit>`。
2. 重新构建前后端。
3. 确认 `/api/health`、`/models`、`/chat/:modelId` 可访问。
4. 若涉及环境变量，恢复上一版 `.env`。
```
