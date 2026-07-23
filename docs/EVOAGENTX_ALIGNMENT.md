# EvoAgentX 对齐审计

最后更新日期：2026-07-22

## 定位

EvoAgentX 是 Xpert 三轮资源收尾后的下一条功能主线。ModelMirror 不把整个上游仓库作为运行时依赖，而是审计并选择性移植对元智能体、评估和自进化真正有价值的 MIT 模块。

当前 `server/meta_agent/` 只实现了较早的 `goal -> sub_tasks -> inferred edges` 规划形态。此后 Workflow 已增加发布版本、资源绑定、Agent 级 middleware、Toolset、Knowledge、Goal、Handoff、Sandbox、Browser、Client Tool、Automation 和 Data X，导致 MetaAgent 生成能力明显落后于可执行画布。

## 许可证与复用规则

- 上游：`EvoAgentX/EvoAgentX`。
- 许可证：MIT；正式移植前必须在本文件锁定具体 commit，并复核目标文件的版权头和依赖许可证。
- 允许：选择性移植独立算法、数据结构和测试，并保留原版权、MIT License 与 NOTICE。
- 禁止：未审计地复制整个仓库、把上游运行时直接嵌入服务、引入许可证不兼容依赖，或让 optimizer 直接修改线上版本。
- Xpert AGPL 源码仍只作领域行为参考，不进入 EvoAgentX MIT 复用清单。

## 审计矩阵

| 能力域 | ModelMirror 当前状态 | 审计重点 | 预期产物 |
| --- | --- | --- | --- |
| Workflow generation | 只能生成基础节点和简单边 | planner schema、节点选择、依赖推断、结构约束 | Meta Planner V2 |
| Evaluation | RAG 有专门评估，通用 Xpert 缺任务级基准 | evaluator 接口、指标组合、candidate/baseline 比较 | 通用评估运行 |
| Benchmark | 无统一 Xpert 任务集 | dataset schema、可重复运行、结果归档 | Benchmark Suite |
| Prompt optimizer | 仅人工提示词编辑 | TextGrad/MIPRO 类优化接口与预算控制 | Prompt 候选提案 |
| Workflow optimizer | 无结构进化 | SEW/AFlow 类候选生成、拓扑变异、安全校验 | Workflow 候选草稿 |
| Memory | 已有会话/Xpert 文件记忆 | 是否存在可复用的反思与经验抽取模块 | 受审批经验候选 |

## 阶段顺序

### 1. `EVOAGENTX-ALIGNMENT-AUDIT-01`

- 锁定上游 commit、Python 版本、依赖树与许可证。
- 逐文件标记 `reuse / adapt / rewrite / reject`。
- 用 ModelMirror 当前 Workflow、XpertVersion、RunRegistry 与 Store 契约建立映射。
- 建立最小 benchmark，确保移植前后可比较。

### 2. `EVOAGENTX-META-PLANNER-01`

- 生成当前完整 `WorkflowNodeKind`，包含 `external_xpert`、`knowledge_base`、未来 `toolset_resource` 和 Agent middleware。
- 特殊绑定边使用 `targetHandle` 契约，不混入控制流。
- 草稿必须通过 `validate_workflow_graph`、Xpert 发布预检和资源存在性检查。
- Planner 只写候选 Xpert 草稿，不自动发布。

### 3. `EVOAGENTX-EVALUATOR-02`

- 引入任务数据集、可插拔指标、候选执行、基线比较和预算统计。
- 评估 run 必须固定 XpertVersion、模型和资源版本。
- 结果保存安全摘要，不保存密钥或不必要的完整用户内容。

### 4. `EVOAGENTX-EVOLUTION-03`

- 先优化 Prompt，再开放工作流结构变异。
- 任何优化都必须生成候选草稿、变更说明和评估报告。
- 只有人工批准后才能进入 Xpert 发布流程；线上版本保持不可变。

## 验收护栏

- Meta Planner 生成的资源绑定边不参与控制流、变量传播和调度。
- 候选运行与基线使用相同输入、版本和预算。
- optimizer 不能访问 API key、`.env`、Runtime Store 物理路径或公开 App token。
- 失败候选不得覆盖当前草稿；并发编辑使用 revision 冲突保护。
- 所有移植代码都有上游 commit、源文件、许可证和本地测试映射。

## 暂缓

- 企业组织权限、多租户配额和远程插件市场。
- GraphRAG 与知识图谱。
- 无人工审核的持续自进化。
- 直接替换 ModelMirror classic runner 或现有 React/FastAPI 架构。
