# 元智能体集成说明

元智能体工作台用于把自然语言目标拆解为可编辑的经典工作流草稿。它借鉴 EvoAgentX 的 `goal -> sub_tasks -> inferred edges` 规划形态，但不引入完整 EvoAgentX 运行时、优化器、RAG 或 MCP 工具链。

最后更新日期：2026-06-24  
维护人：模镜团队

## 功能范围

- 前端入口：`/agents/meta-agent`。
- 后端接口：`POST /api/meta-agent/generate-workflow`。
- 后端模块：`server/meta_agent/`。
- 输出目标：生成 `WorkflowDefinition`，可导入经典自研画布并通过 `/api/workflow/run` 执行。
- 校验路径：生成后的工作流会调用 `workflow_native.validate_workflow_graph` 做静态校验。

## 请求示例

```bash
curl -X POST http://localhost:8000/api/meta-agent/generate-workflow \
  -H "Content-Type: application/json" \
  -d "{\"goal\":\"为一个新产品发布生成包含需求拆解、风险评估和上线清单的工作流。\",\"model_id\":\"deepseek/deepseek-chat\",\"temperature\":0.2,\"max_tasks\":5}"
```

## 实现边界

- planner、schema 和 prompt 放在 `server/meta_agent/`，不要继续堆进 `server/main.py`。
- 生成接口依赖模型网关；测试必须 mock `collect_chat_completion_text`，不能请求真实模型。
- 前端只负责提交目标、展示任务拆解和导入经典画布，不持久化服务端状态。
- Docker 镜像必须复制 `server/meta_agent/`，否则 `server/main.py` 导入会失败。

## 验证命令

```bash
python -m py_compile server/main.py server/meta_agent/*.py
python -m pytest server/tests/test_meta_agent.py -q
cd client
npm.cmd run build
docker compose -p modelmirror up -d --build --force-recreate
```

容器启动后检查：

```bash
curl http://localhost:8000/api/health
curl http://localhost:5173/agents/meta-agent
```

## 归因

本模块参考 EvoAgentX 的规划概念，详见 `server/meta_agent/NOTICE.md`。
