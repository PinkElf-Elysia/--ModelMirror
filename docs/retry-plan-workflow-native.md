# 自研工作流引擎重试路线

日期：2026-06-10  
目标：在不影响 Dify 稳定集成的前提下，逐步建设模镜原生工作流和 RAG 能力。

## 总原则

- Dify iframe + 后端代理继续作为 `/workflow` 和 `/rag` 的稳定主路径。
- 自研能力必须使用独立路由，例如 `/workflow-native` 和 `/rag-native`。
- 每个阶段必须可单独发布、单独验证、单独回滚。
- 每个阶段结束时必须运行前端构建、后端语法检查和对应测试。

## 阶段 1：架构设计与接口定义

### 目标

先完成文档和类型定义，不写生产逻辑。

### 输出

- `docs/workflow-native-design.md`
- TypeScript 类型草案：Workflow、Node、Edge、Variable、ExecutionResult。
- 后端接口契约草案：
  - `POST /api/workflow-native/validate`
  - `POST /api/workflow-native/run`
  - `GET /api/workflow-native/templates`
- 节点能力矩阵：
  - Input
  - LLM
  - Output
  - Condition
  - Code
  - Retriever
  - Tool

### 验收标准

- 设计文档能解释数据流、状态流、错误流和回退策略。
- 至少一次架构评审通过。
- 不修改 `/workflow` 和 `/rag` 稳定入口。

## 阶段 2：后端执行器 MVP

### 目标

实现纯后端线性执行器，不做前端 UI。

### 范围

- 支持 Input、LLM、Output 三种节点。
- 支持变量模板 `{{user_input}}`。
- 支持拓扑排序和循环检测。
- 支持 dry-run，不调用真实模型也能验证变量传递。

### 测试

至少 5 个测试用例：

1. 输入节点把变量写入上下文。
2. LLM 节点能接收模板渲染后的 prompt。
3. Output 节点能输出指定变量。
4. 缺失变量时返回结构化错误。
5. 图中存在循环时拒绝执行。

### 验收标准

- `python -m pytest` 通过。
- `POST /api/workflow-native/run` 可通过 curl 验证。
- 单步非模型执行耗时小于 500ms。

## 阶段 3：前端编辑器 MVP

### 目标

在独立路由 `/workflow-native` 中实现最小可用 React Flow 编辑器。

### 范围

- 支持添加 Input、LLM、Output 节点。
- 支持连线、保存到 localStorage、加载草稿。
- 支持调用阶段 2 后端接口运行。
- 运行结果以节点日志形式展示。

### 验收标准

- 能创建“输入 → LLM → 输出”工作流并运行。
- Dify 版 `/workflow` 不受影响。
- 前端 `npm run build` 通过。

## 阶段 4：增量增强节点系统

### 目标

按节点逐个增强，而不是一次扩满。

### 顺序

1. Condition：支持 equals、contains、exists。
2. Code：仅支持预置字符串函数，禁止任意代码执行。
3. Retriever：调用资料库检索接口。
4. Tool：先接入静态工具清单，再考虑 MCP。

### 每个节点的强制要求

- 后端执行逻辑。
- 前端节点配置面板。
- 至少 3 个测试用例。
- 错误状态和空状态文案。

### 验收标准

- 新节点测试通过。
- 原有节点测试不回归。
- UI 能展示节点执行状态和错误信息。

## 阶段 5：RAG 自研替换

### 目标

在 Dify 资料库仍可用的情况下，建设自研 RAG 管道。

### 范围

- 文档上传。
- 文本抽取。
- 分段策略。
- Embedding 生成。
- 向量存储。
- Top K 检索。
- 在面试间中选择资料库作为上下文增强源。

### 接口兼容

尽量对齐 Dify 知识库概念：

- Dataset
- Document
- Segment
- Retrieval Test
- App Binding

### 验收标准

- 上传一个 PDF 后可完成抽取、分段、索引。
- 在面试间提问时能命中相关片段。
- RAG 失败时可一键回退到 Dify 资料库。

## 发布策略

- 阶段 1 到阶段 3 只能作为实验入口发布。
- 阶段 4 完成前不得替换 `/workflow` 主路由。
- 阶段 5 完成前不得替换 `/rag` 主路由。
- 任一阶段失败时，产品仍保持 Dify 稳定路径可用。
