# 元智能体集成说明

最后更新日期：2026-07-22
维护人：模镜团队

## 定位

元智能体工作台用于把自然语言目标拆解为可编辑的经典工作流/Xpert 草稿。当前模块能生成基础节点和 inferred edges，也能进入 AgentTask、Handoff、RunRegistry 与 Xpert 草稿链路；但它尚不能可靠生成后续新增的资源绑定、中间件、知识能力和完整发布契约。

早期实现参考 EvoAgentX 的 `goal -> sub_tasks -> inferred edges` 规划形态，归因保留在 `server/meta_agent/NOTICE.md`。在 Xpert 的资源节点、Toolset、Plugin/Prompt 三轮收尾后，元智能体将成为 EvoAgentX 主线的首要升级对象：先审计 MIT 上游，再让 Meta Planner V2 生成当前完整节点、资源绑定与中间件，而不是继续输出过时的 `agent` 长链。

## 功能范围

- 前端入口：`/agents/meta-agent`。
- 后端生成接口：`POST /api/meta-agent/generate-workflow`。
- 后端模块：`server/meta_agent/`。
- 任务运行时：复用 `POST /api/runtime/agent-tasks`、`GET /api/runtime/agent-tasks`、`GET /api/runtime/agent-tasks/{task_id}`、`POST /api/runtime/agent-tasks/{task_id}/cancel`。
- Handoff Inbox：任务工作台会查询 `GET /api/runtime/agent-tasks/{task_id}/handoffs` 展示选中任务的移交记录，并通过 `GET /api/runtime/agent-handoffs?status=&target_agent=&limit=20` 提供 Handoff Inbox Beta；pending 移交支持手动接受/拒绝，accepted 移交支持填写完成结果并提交。
- 输出目标：生成 `WorkflowDefinition`，可导入经典自研画布、保存为 Xpert 草稿并通过 `/api/workflow/run` 执行。
- 校验路径：生成后的工作流会调用 `workflow_native.validate_workflow_graph` 做静态校验。

## 实现边界

- planner、schema 和 prompt 放在 `server/meta_agent/`，不要继续堆进 `server/main.py`。
- 生成接口依赖模型网关；测试必须 mock `collect_chat_completion_text`，不能请求真实模型。
- 前端负责提交目标、展示任务拆解、创建 AgentTask 记录、展示任务工作台和导入经典画布。
- HandoffExecutor 与 GoalCoordinator 已能执行固定版本 Xpert；元智能体生成器本身仍只负责规划和草稿，不直接发布、不静默调度，也不具备自进化评估闭环。
- 当前 generator 对 `external_xpert`、`knowledge_base`、Agent 级 middleware、Toolset 资源和知识画布配置的生成能力滞后，进入 EvoAgentX 审计后的首批修复范围。
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

1. `EVOAGENTX-ALIGNMENT-AUDIT-01`：锁定上游 commit、MIT 许可证、可复用模块和独立重写边界。
2. `EVOAGENTX-META-PLANNER-01`：让 planner 生成当前完整 WorkflowNodeKind、资源绑定边、Agent middleware 与发布预检所需配置。
3. `EVOAGENTX-EVALUATOR-02`：增加任务数据集、可插拔指标、候选执行和基线对比。
4. `EVOAGENTX-EVOLUTION-03`：先做 Prompt 优化，再做工作流结构优化；输出候选草稿与评估报告，必须人工批准后才能发布。
