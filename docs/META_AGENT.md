# 元智能体集成说明

最后更新日期：2026-06-26  
维护人：模镜团队

## 定位

元智能体工作台用于把自然语言目标拆解为可编辑的经典工作流草稿。当前模块已转入 Xpert 对齐主线：它复用现有 Agent Task Runtime 做任务可见、详情查看和取消，不实现真实多 Agent 调度。

早期实现曾参考 EvoAgentX 的 `goal -> sub_tasks -> inferred edges` 规划形态；该参考现在仅作为历史归因保留在 `server/meta_agent/NOTICE.md`。后续规划优先对齐 Xpert 的 Agent、Handoff、Workflow、Toolset 与运行观测能力。

## 功能范围

- 前端入口：`/agents/meta-agent`。
- 后端生成接口：`POST /api/meta-agent/generate-workflow`。
- 后端模块：`server/meta_agent/`。
- 任务运行时：复用 `POST /api/runtime/agent-tasks`、`GET /api/runtime/agent-tasks`、`GET /api/runtime/agent-tasks/{task_id}`、`POST /api/runtime/agent-tasks/{task_id}/cancel`。
- 输出目标：生成 `WorkflowDefinition`，可导入经典自研画布并通过 `/api/workflow/run` 执行。
- 校验路径：生成后的工作流会调用 `workflow_native.validate_workflow_graph` 做静态校验。

## 实现边界

- planner、schema 和 prompt 放在 `server/meta_agent/`，不要继续堆进 `server/main.py`。
- 生成接口依赖模型网关；测试必须 mock `collect_chat_completion_text`，不能请求真实模型。
- 前端负责提交目标、展示任务拆解、创建 AgentTask 记录、展示任务工作台和导入经典画布。
- 当前只做任务可见和取消，不做队列分派、专家协作、自动执行或持久化调度。
- Docker 镜像必须复制 `server/meta_agent/`，否则 `server/main.py` 导入会失败。

## 请求示例

```bash
curl -X POST http://localhost:8000/api/meta-agent/generate-workflow \
  -H "Content-Type: application/json" \
  -d "{\"goal\":\"为一个新产品发布生成包含需求拆解、风险评估和上线清单的工作流。\",\"model_id\":\"deepseek/deepseek-chat\",\"temperature\":0.2,\"max_tasks\":5}"
```

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

## 后续路线

1. 将 AgentTask 扩展到 Handoff API，支持任务移交、接受、拒绝和完成。
2. 在经典工作流中增加 handoff / sub-agent 相关节点。
3. 将任务工作台从“可见与取消”升级为 Xpert 风格 RunRegistry 视图。
4. 在 Xpert 对齐主线稳定后，再评估是否补齐 EvoAgentX 历史参考中的剩余能力。
