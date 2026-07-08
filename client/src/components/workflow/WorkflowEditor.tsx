import {
  addEdge,
  Background,
  BackgroundVariant,
  Controls,
  MiniMap,
  Panel,
  ReactFlow,
  ReactFlowProvider,
  useEdgesState,
  useNodesState,
  useReactFlow,
  type Connection,
  type NodeChange,
  type EdgeChange,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useCallback, useEffect, useMemo, useState } from "react";
import { models } from "../../data/models";
import {
  type CodeOperation,
  type ConditionOperator,
  type HttpRequestMethod,
  type ListOperationOperator,
  type WorkflowDefinition,
  type WorkflowEdge,
  type WorkflowNode,
  type WorkflowNodeData,
  type WorkflowNodeKind,
} from "../../types/workflow";
import { type RuntimeMiddlewareField } from "../../types/runtimeMiddleware";
import { readStoredWorkflow, saveStoredWorkflow } from "../../utils/workflowStorage";
import NodePalette from "./NodePalette";
import WorkflowNodeCard from "./WorkflowNodeCard";
import WorkflowRun from "./WorkflowRun";

const nodeTypes = {
  workflowNode: WorkflowNodeCard,
};

interface RuntimeMiddlewareDragPayload {
  kind: "runtime_middleware";
  runtimeMiddlewareId?: string;
  runtimeMiddlewareKind?: string;
  title?: string;
  description?: string;
  fields?: RuntimeMiddlewareField[];
  metadata?: Record<string, unknown>;
}

const runtimeMiddlewareFieldTypes = new Set([
  "text",
  "textarea",
  "select",
  "boolean",
  "number",
  "json",
]);

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function isRuntimeMiddlewareField(value: unknown): value is RuntimeMiddlewareField {
  return (
    isRecord(value) &&
    typeof value.name === "string" &&
    typeof value.label === "string" &&
    typeof value.type === "string" &&
    runtimeMiddlewareFieldTypes.has(value.type)
  );
}

function parseRuntimeMiddlewarePayload(
  raw: string,
): RuntimeMiddlewareDragPayload | null {
  if (!raw.trim().startsWith("{")) {
    return null;
  }

  try {
    const parsed: unknown = JSON.parse(raw);
    if (!isRecord(parsed) || parsed.kind !== "runtime_middleware") {
      return null;
    }

    return {
      kind: "runtime_middleware",
      runtimeMiddlewareId:
        typeof parsed.runtimeMiddlewareId === "string"
          ? parsed.runtimeMiddlewareId
          : undefined,
      runtimeMiddlewareKind:
        typeof parsed.runtimeMiddlewareKind === "string"
          ? parsed.runtimeMiddlewareKind
          : undefined,
      title: typeof parsed.title === "string" ? parsed.title : undefined,
      description:
        typeof parsed.description === "string" ? parsed.description : undefined,
      fields: Array.isArray(parsed.fields)
        ? parsed.fields.filter(isRuntimeMiddlewareField)
        : [],
      metadata: isRecord(parsed.metadata) ? parsed.metadata : {},
    };
  } catch {
    return null;
  }
}

function createRuntimeMiddlewareConfig(
  fields: RuntimeMiddlewareField[],
): Record<string, unknown> {
  return fields.reduce<Record<string, unknown>>((config, field) => {
    if (field.default !== undefined) {
      config[field.name] = field.default;
    }
    return config;
  }, {});
}

function createNodeData(
  kind: WorkflowNodeKind,
  payload?: RuntimeMiddlewareDragPayload,
): WorkflowNodeData {
  if (kind === "input") {
    return {
      kind,
      title: "接待处输入",
      description: "收集用户给流水线的原始任务。",
      variableName: "user_input",
    };
  }

  if (kind === "llm") {
    return {
      kind,
      title: "模型工位",
      description: "调用模型，把上游变量加工成新结果。",
      modelId: "deepseek/deepseek-chat",
      prompt: "请基于以下输入给出清晰回答：\n\n{{user_input}}",
      outputVariable: "llm_output",
    };
  }

  if (kind === "condition") {
    return {
      kind,
      title: "分流判断",
      description: "根据变量内容决定走“是”或“否”。",
      conditionVariable: "user_input",
      conditionOperator: "contains",
      conditionValue: "代码",
    };
  }

  if (kind === "code") {
    return {
      kind,
      title: "安全加工",
      description: "只执行预置字符串操作，不运行任意代码。",
      codeOperation: "upper",
      codeInputVariable: "llm_output",
      codeOutputVariable: "code_output",
      replaceFrom: "",
      replaceTo: "",
      concatValue: "",
      pythonCode: "print(input)",
    };
  }

  if (kind === "variable_assign") {
    return {
      kind,
      title: "变量赋值",
      description: "把模板内容写入一个新变量。",
      variableName: "assigned_text",
      template: "收到：{{user_input}}",
    };
  }

  if (kind === "template_transform") {
    return {
      kind,
      title: "模板转换",
      description: "把变量填入长文本模板，产出报告或结构化文本。",
      template: "## 处理结果\n\n用户输入：{{user_input}}\n",
      outputVariable: "template_output",
    };
  }

  if (kind === "variable_aggregator") {
    return {
      kind,
      title: "变量聚合器",
      description: "汇总多个变量，便于下游统一处理。",
      variableNames: "user_input",
      outputTemplate: "{name}={value}\n",
      outputVariable: "aggregated_output",
    };
  }

  if (kind === "parameter_extractor") {
    return {
      kind,
      title: "参数提取器",
      description: "调用模型从文本中抽取字段，返回 JSON 字符串。",
      inputVariable: "user_input",
      schema: "name: 姓名\nemail_address: 邮箱地址",
      modelId: "deepseek/deepseek-chat",
      outputVariable: "parameters_json",
    };
  }

  if (kind === "knowledge_retrieval") {
    return {
      kind,
      title: "知识检索",
      description: "使用本地 RAG 资料库检索相关片段。",
      queryVariable: "user_input",
      top_k: "3",
      outputVariable: "rag_context",
    };
  }

  if (kind === "knowledge_citation") {
    return {
      kind,
      title: "知识引用锚点",
      description: "把本地 RAG 检索结果转换为 CitationAnchor JSON。",
      queryVariable: "user_input",
      knowledgeBaseId: "",
      top_k: "4",
      outputVariable: "citation_anchors_json",
    };
  }

  if (kind === "document_extractor") {
    return {
      kind,
      title: "文档提取器",
      description: "从受限本地文件路径中提取纯文本。",
      sourcePathVariable: "document_path",
      outputVariable: "document_text",
    };
  }

  if (kind === "human_intervention") {
    return {
      kind,
      title: "人工确认",
      description: "暂停流水线，等待用户补充文本后继续。",
      prompt: "请确认或补充这段内容：\n\n{{user_input}}",
      outputVariable: "human_input",
    };
  }

  if (kind === "question_classifier") {
    return {
      kind,
      title: "问题分类",
      description: "关键词规则分类",
      inputVariable: "user_input",
      categories:
        '{"投诉":["差","投诉","退款"],"咨询":["咨询","如何","怎么"],"订单":["订单","下单","购买"],"售后":["售后","退货","换"]}',
      outputVariable: "category",
      defaultCategory: "未知",
      matchMode: "contains_any",
      caseSensitive: "false",
      useLlmFallback: "false",
      modelId: "",
      llmFallbackPrompt: "",
    };
  }

  if (kind === "agent") {
    return {
      kind,
      title: "Agent",
      description: "模型驱动的任务执行节点。",
      agentMode: "tool_first",
      instruction: "{{user_input}}",
      modelId: "",
      toolNames: "",
      outputVariable: "agent_output",
      maxIterations: "5",
      temperature: "0.7",
      promptSuffix: "",
    };
  }

  if (kind === "workflow_agent") {
    return {
      kind,
      title: "工作流智能体",
      description: "模型驱动的单步智能体执行节点。",
      agentName: "workflow-agent",
      modelId: "deepseek/deepseek-chat",
      rolePrompt: "你是负责执行当前工作流步骤的智能体，请直接输出结果。",
      taskInput: "{{user_input}}",
      toolMode: "none",
      toolNames: "",
      maxIterations: "5",
      promptSuffix: "",
      outputVariable: "agent_output",
    };
  }

  if (kind === "agent_task") {
    return {
      kind,
      title: "智能体任务",
      description: "创建 Agent Task Runtime 任务，并把 task_id 写入变量。",
      taskTitle: "工作流任务：{{user_input}}",
      taskInput: "{{user_input}}",
      assignedAgent: "workflow-planner",
      outputVariable: "agent_task_id",
    };
  }

  if (kind === "agent_handoff") {
    return {
      kind,
      title: "智能体移交",
      description: "将已有 Agent Task 移交给另一个智能体，输出 handoff_id。",
      taskIdVariable: "agent_task_id",
      sourceAgent: "workflow-planner",
      targetAgent: "review-agent",
      reason: "请接手处理：{{user_input}}",
      outputVariable: "agent_handoff_id",
    };
  }

  if (kind === "handoff_router") {
    return {
      kind,
      title: "移交路由器",
      description: "读取工作流智能体输出，创建 AgentTask 并投递 pending Handoff。",
      sourceVariable: "agent_output",
      taskTitle: "来自工作流智能体的任务",
      targetAgent: "review-agent",
      sourceAgent: "workflow-agent",
      reasonTemplate: "请处理工作流智能体输出：{{agent_output}}",
      outputVariable: "agent_handoff_id",
    };
  }

  if (kind === "mcp_tool") {
    return {
      kind,
      title: "MCP Tool",
      description: "调用已注册的 MCP 工具",
      toolName: "",
      argumentsJson: "{}",
      outputVariable: "mcp_output",
      errorMode: "fail_safe",
    };
  }

  if (kind === "time_tool") {
    return {
      kind,
      title: "时间工具",
      description: "获取当前时间或格式化日期",
      operation: "now_iso",
      formatString: "%Y-%m-%d %H:%M:%S",
      outputVariable: "current_time",
    };
  }

  if (kind === "http_request") {
    return {
      kind,
      title: "HTTP 请求",
      description: "调用一个外部接口并保存响应文本。默认运行器不会真实出站。",
      url: "https://example.com",
      method: "GET",
      headersJson: "",
      bodyVariable: "",
      outputVariable: "http_output",
    };
  }

  if (kind === "list_operation") {
    return {
      kind,
      title: "列表操作",
      description: "把逗号分隔文本当作列表做轻量处理。",
      inputVariable: "user_input",
      operator: "length",
      joinSeparator: " / ",
      outputVariable: "list_output",
    };
  }

  if (kind === "iteration") {
    return {
      kind,
      title: "迭代处理",
      description: "逐项渲染模板，把结果汇总为 JSON 数组字符串。",
      inputVariable: "user_input",
      iterationVariable: "item",
      itemTemplate: "处理：{{item}}",
      outputVariable: "iteration_output",
    };
  }

  if (kind === "runtime_middleware") {
    const fields = payload?.fields ?? [];
    const middlewareId = payload?.runtimeMiddlewareId ?? "unknown";
    const middlewareKind =
      payload?.runtimeMiddlewareKind ?? "runtime_middleware.unknown";
    return {
      kind,
      title: payload?.title ?? "中间件节点",
      description: payload?.description ?? "运行时中间件原型节点。",
      runtimeMiddlewareId: middlewareId,
      runtimeMiddlewareKind: middlewareKind,
      runtimeMiddlewareFields: fields,
      runtimeMiddlewareMetadata: payload?.metadata ?? {},
      runtimeMiddlewareConfig: createRuntimeMiddlewareConfig(fields),
    };
  }

  return {
    kind,
    title: "最终交付",
    description: "把指定变量作为工作流结果交付。",
    outputVariable: "llm_output",
  };
}

function createNode(
  kind: WorkflowNodeKind,
  x: number,
  y: number,
  payload?: RuntimeMiddlewareDragPayload,
): WorkflowNode {
  return {
    id: `${kind}-${Date.now()}-${Math.random().toString(16).slice(2, 7)}`,
    type: "workflowNode",
    position: { x, y },
    data: createNodeData(kind, payload),
  };
}

function initialDefinition(workflowId: string): WorkflowDefinition {
  const inputNode: WorkflowNode = {
    id: "input-1",
    type: "workflowNode",
    position: { x: 0, y: 80 },
    data: createNodeData("input"),
  };
  const llmNode: WorkflowNode = {
    id: "llm-1",
    type: "workflowNode",
    position: { x: 340, y: 80 },
    data: createNodeData("llm"),
  };
  const outputNode: WorkflowNode = {
    id: "output-1",
    type: "workflowNode",
    position: { x: 700, y: 80 },
    data: createNodeData("output"),
  };

  return {
    id: workflowId,
    title: "新建 AI 流水线",
    nodes: [inputNode, llmNode, outputNode],
    edges: [
      {
        id: "edge-input-llm",
        source: inputNode.id,
        target: llmNode.id,
      },
      {
        id: "edge-llm-output",
        source: llmNode.id,
        target: outputNode.id,
      },
    ],
    updatedAt: new Date().toISOString(),
  };
}

function loadDefinition(workflowId: string) {
  return readStoredWorkflow(workflowId) ?? initialDefinition(workflowId);
}

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <label className="block">
      <span className="text-xs font-semibold text-slate-300">{label}</span>
      <div className="mt-2">{children}</div>
    </label>
  );
}

function textInputClass() {
  return "w-full rounded-lg border border-white/10 bg-white/[0.055] px-3 py-2 text-sm text-white outline-none transition placeholder:text-slate-500 focus:border-brand-300/50 focus:ring-4 focus:ring-brand-300/10";
}

function runtimeMiddlewareFieldValue(
  config: Record<string, unknown> | undefined,
  field: RuntimeMiddlewareField,
): unknown {
  if (config && Object.prototype.hasOwnProperty.call(config, field.name)) {
    return config[field.name];
  }
  return field.default;
}

function runtimeMiddlewareStringValue(
  config: Record<string, unknown> | undefined,
  field: RuntimeMiddlewareField,
): string {
  const value = runtimeMiddlewareFieldValue(config, field);
  if (value === undefined || value === null) {
    return "";
  }
  if (typeof value === "string") {
    return value;
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  return JSON.stringify(value, null, 2);
}

function runtimeMiddlewareBooleanValue(
  config: Record<string, unknown> | undefined,
  field: RuntimeMiddlewareField,
): boolean {
  const value = runtimeMiddlewareFieldValue(config, field);
  if (typeof value === "boolean") {
    return value;
  }
  if (typeof value === "string") {
    return value.toLowerCase() === "true";
  }
  return false;
}

interface RegistryToolOption {
  name: string;
  description?: string;
}

function isRegistryToolOption(value: unknown): value is RegistryToolOption {
  return (
    typeof value === "object" &&
    value !== null &&
    "name" in value &&
    typeof (value as { name?: unknown }).name === "string"
  );
}

interface NodeConfigProps {
  node: WorkflowNode | null;
  onChange: (nodeId: string, data: Partial<WorkflowNodeData>) => void;
}

function NodeConfig({ node, onChange }: NodeConfigProps) {
  const [registryTools, setRegistryTools] = useState<RegistryToolOption[]>([]);
  const [registryToolsError, setRegistryToolsError] = useState("");

  useEffect(() => {
    let cancelled = false;

    async function loadRegistryTools() {
      try {
        const response = await fetch("/api/registry/tools");
        if (!response.ok) {
          throw new Error("工具注册表暂时不可用。");
        }
        const payload: unknown = await response.json();
        const tools = Array.isArray(payload)
          ? payload.filter(isRegistryToolOption)
          : [];
        if (!cancelled) {
          setRegistryTools(tools);
          setRegistryToolsError("");
        }
      } catch (error) {
        if (!cancelled) {
          setRegistryTools([]);
          setRegistryToolsError(
            error instanceof Error ? error.message : "工具注册表加载失败。",
          );
        }
      }
    }

    void loadRegistryTools();

    return () => {
      cancelled = true;
    };
  }, []);

  if (!node) {
    return (
      <div className="rounded-lg border border-dashed border-white/15 bg-white/[0.035] px-4 py-8 text-center text-sm leading-6 text-slate-400">
        点击画布上的工位牌，即可编辑节点配置。
      </div>
    );
  }

  const data = node.data;
  const update = (patch: Partial<WorkflowNodeData>) => onChange(node.id, patch);
  const runtimeMiddlewareConfig = isRecord(data.runtimeMiddlewareConfig)
    ? data.runtimeMiddlewareConfig
    : undefined;
  const updateRuntimeMiddlewareConfig = (fieldName: string, value: unknown) =>
    update({
      runtimeMiddlewareConfig: {
        ...(runtimeMiddlewareConfig ?? {}),
        [fieldName]: value,
      },
    });

  return (
    <div className="space-y-4">
      <Field label="工位名称">
        <input
          className={textInputClass()}
          onChange={(event) => update({ title: event.target.value })}
          value={data.title}
        />
      </Field>

      <Field label="说明">
        <textarea
          className={`${textInputClass()} min-h-20 resize-none leading-6`}
          onChange={(event) => update({ description: event.target.value })}
          value={data.description}
        />
      </Field>

      {data.kind === "input" ? (
        <Field label="输入变量名">
          <input
            className={textInputClass()}
            onChange={(event) => update({ variableName: event.target.value })}
            value={data.variableName ?? ""}
          />
        </Field>
      ) : null}

      {data.kind === "llm" ? (
        <>
          <Field label="调用模型">
            <select
              className={textInputClass()}
              onChange={(event) => update({ modelId: event.target.value })}
              value={data.modelId ?? "deepseek/deepseek-chat"}
            >
              {models.map((model) => (
                <option
                  className="bg-slate-950 text-white"
                  key={model.id}
                  value={model.id}
                >
                  {model.name}
                </option>
              ))}
            </select>
          </Field>
          <Field label="提示词（支持 {{变量}}）">
            <textarea
              className={`${textInputClass()} min-h-36 resize-none leading-6`}
              onChange={(event) => update({ prompt: event.target.value })}
              value={data.prompt ?? ""}
            />
          </Field>
          <Field label="输出变量名">
            <input
              className={textInputClass()}
              onChange={(event) => update({ outputVariable: event.target.value })}
              value={data.outputVariable ?? ""}
            />
          </Field>
        </>
      ) : null}

      {data.kind === "condition" ? (
        <>
          <Field label="判断变量">
            <input
              className={textInputClass()}
              onChange={(event) =>
                update({ conditionVariable: event.target.value })
              }
              value={data.conditionVariable ?? ""}
            />
          </Field>
          <Field label="判断方式">
            <select
              className={textInputClass()}
              onChange={(event) =>
                update({
                  conditionOperator: event.target.value as ConditionOperator,
                })
              }
              value={data.conditionOperator ?? "contains"}
            >
              <option className="bg-slate-950" value="contains">
                包含
              </option>
              <option className="bg-slate-950" value="equals">
                等于
              </option>
            </select>
          </Field>
          <Field label="比较值">
            <input
              className={textInputClass()}
              onChange={(event) => update({ conditionValue: event.target.value })}
              value={data.conditionValue ?? ""}
            />
          </Field>
        </>
      ) : null}

      {data.kind === "code" ? (
        <>
          <div className="rounded-lg border border-amber-300/25 bg-amber-300/10 px-3 py-2 text-xs leading-5 text-amber-50">
            安全提示：MVP 不执行任意代码，仅提供 upper、lower、replace、concat 四种字符串操作。
          </div>
          <Field label="内置操作">
            <select
              className={textInputClass()}
              onChange={(event) =>
                update({ codeOperation: event.target.value as CodeOperation })
              }
              value={data.codeOperation ?? "upper"}
            >
              <option className="bg-slate-950" value="upper">
                转大写
              </option>
              <option className="bg-slate-950" value="lower">
                转小写
              </option>
              <option className="bg-slate-950" value="replace">
                替换
              </option>
              <option className="bg-slate-950" value="concat">
                拼接
              </option>
              <option className="bg-slate-950" value="python">
                Python sandbox
              </option>
            </select>
          </Field>
          <Field label="输入变量">
            <input
              className={textInputClass()}
              onChange={(event) =>
                update({ codeInputVariable: event.target.value })
              }
              value={data.codeInputVariable ?? ""}
            />
          </Field>
          <Field label="输出变量">
            <input
              className={textInputClass()}
              onChange={(event) =>
                update({ codeOutputVariable: event.target.value })
              }
              value={data.codeOutputVariable ?? ""}
            />
          </Field>
          {data.codeOperation === "replace" ? (
            <div className="grid grid-cols-2 gap-3">
              <Field label="把">
                <input
                  className={textInputClass()}
                  onChange={(event) => update({ replaceFrom: event.target.value })}
                  value={data.replaceFrom ?? ""}
                />
              </Field>
              <Field label="替换为">
                <input
                  className={textInputClass()}
                  onChange={(event) => update({ replaceTo: event.target.value })}
                  value={data.replaceTo ?? ""}
                />
              </Field>
            </div>
          ) : null}
          {data.codeOperation === "concat" ? (
            <Field label="追加内容">
              <input
                className={textInputClass()}
                onChange={(event) => update({ concatValue: event.target.value })}
                value={data.concatValue ?? ""}
              />
            </Field>
          ) : null}
          {data.codeOperation === "python" ? (
            <Field label="Python 代码">
              <textarea
                className={`${textInputClass()} min-h-40 resize-none font-mono text-xs leading-5`}
                onChange={(event) => update({ pythonCode: event.target.value })}
                placeholder="print(len(input.split()))"
                value={data.pythonCode ?? ""}
              />
              <p className="mt-2 text-xs leading-5 text-slate-400">
                可用变量：input（输入变量内容）和 variables（全部变量字典）。请用 print() 输出结果。
              </p>
            </Field>
          ) : null}
        </>
      ) : null}

      {data.kind === "variable_assign" ? (
        <>
          <Field label="写入变量名">
            <input
              className={textInputClass()}
              onChange={(event) => update({ variableName: event.target.value })}
              value={data.variableName ?? ""}
            />
          </Field>
          <Field label="赋值模板（支持 {{变量}}）">
            <textarea
              className={`${textInputClass()} min-h-28 resize-none leading-6`}
              onChange={(event) => update({ template: event.target.value })}
              value={data.template ?? ""}
            />
          </Field>
        </>
      ) : null}

      {data.kind === "template_transform" ? (
        <>
          <Field label="模板内容（支持 {{变量}}）">
            <textarea
              className={`${textInputClass()} min-h-36 resize-none leading-6`}
              onChange={(event) => update({ template: event.target.value })}
              value={data.template ?? ""}
            />
          </Field>
          <Field label="输出变量">
            <input
              className={textInputClass()}
              onChange={(event) => update({ outputVariable: event.target.value })}
              value={data.outputVariable ?? ""}
            />
          </Field>
        </>
      ) : null}

      {data.kind === "variable_aggregator" ? (
        <>
          <Field label="变量名列表（逗号分隔）">
            <input
              className={textInputClass()}
              onChange={(event) => update({ variableNames: event.target.value })}
              value={data.variableNames ?? ""}
            />
          </Field>
          <Field label="输出模板（可选，支持 {name} / {value}）">
            <textarea
              className={`${textInputClass()} min-h-24 resize-none font-mono text-xs leading-5`}
              onChange={(event) => update({ outputTemplate: event.target.value })}
              value={data.outputTemplate ?? ""}
            />
          </Field>
          <Field label="输出变量">
            <input
              className={textInputClass()}
              onChange={(event) => update({ outputVariable: event.target.value })}
              value={data.outputVariable ?? ""}
            />
          </Field>
        </>
      ) : null}

      {data.kind === "parameter_extractor" ? (
        <>
          <Field label="待提取文本变量">
            <input
              className={textInputClass()}
              onChange={(event) => update({ inputVariable: event.target.value })}
              value={data.inputVariable ?? ""}
            />
          </Field>
          <Field label="调用模型">
            <select
              className={textInputClass()}
              onChange={(event) => update({ modelId: event.target.value })}
              value={data.modelId ?? "deepseek/deepseek-chat"}
            >
              {models.map((model) => (
                <option
                  className="bg-slate-950 text-white"
                  key={model.id}
                  value={model.id}
                >
                  {model.name}
                </option>
              ))}
            </select>
          </Field>
          <Field label="字段描述">
            <textarea
              className={`${textInputClass()} min-h-28 resize-none leading-6`}
              onChange={(event) => update({ schema: event.target.value })}
              value={data.schema ?? ""}
            />
          </Field>
          <Field label="输出变量">
            <input
              className={textInputClass()}
              onChange={(event) => update({ outputVariable: event.target.value })}
              value={data.outputVariable ?? ""}
            />
          </Field>
        </>
      ) : null}

      {data.kind === "knowledge_retrieval" ? (
        <>
          <Field label="查询变量">
            <input
              className={textInputClass()}
              onChange={(event) => update({ queryVariable: event.target.value })}
              value={data.queryVariable ?? ""}
            />
          </Field>
          <Field label="返回片段数 Top K">
            <input
              className={textInputClass()}
              inputMode="numeric"
              onChange={(event) => update({ top_k: event.target.value })}
              type="number"
              value={data.top_k ?? "3"}
            />
          </Field>
          <Field label="输出变量">
            <input
              className={textInputClass()}
              onChange={(event) => update({ outputVariable: event.target.value })}
              value={data.outputVariable ?? ""}
            />
          </Field>
        </>
      ) : null}

      {data.kind === "knowledge_citation" ? (
        <>
          <div className="rounded-lg border border-teal-300/25 bg-teal-300/10 px-3 py-2 text-xs leading-5 text-teal-50">
            输出为 JSON 字符串，包含 citations 与 citation_count；不返回本地文件路径或向量内容。
          </div>
          <Field label="查询变量">
            <input
              className={textInputClass()}
              onChange={(event) => update({ queryVariable: event.target.value })}
              value={data.queryVariable ?? ""}
            />
          </Field>
          <Field label="知识库 ID（可选）">
            <input
              className={textInputClass()}
              onChange={(event) => update({ knowledgeBaseId: event.target.value })}
              placeholder="留空时使用第一个知识库"
              value={data.knowledgeBaseId ?? ""}
            />
          </Field>
          <Field label="返回引用数 Top K">
            <input
              className={textInputClass()}
              inputMode="numeric"
              max={10}
              min={1}
              onChange={(event) => update({ top_k: event.target.value })}
              type="number"
              value={data.top_k ?? "4"}
            />
          </Field>
          <Field label="输出变量">
            <input
              className={textInputClass()}
              onChange={(event) => update({ outputVariable: event.target.value })}
              value={data.outputVariable ?? ""}
            />
          </Field>
        </>
      ) : null}

      {data.kind === "document_extractor" ? (
        <>
          <div className="rounded-lg border border-amber-300/25 bg-amber-300/10 px-3 py-2 text-xs leading-5 text-amber-50">
            安全提示：该节点只读取后端允许目录内的本地文件路径，不提供上传能力。
          </div>
          <Field label="文件路径变量">
            <input
              className={textInputClass()}
              onChange={(event) =>
                update({ sourcePathVariable: event.target.value })
              }
              value={data.sourcePathVariable ?? ""}
            />
          </Field>
          <Field label="输出变量">
            <input
              className={textInputClass()}
              onChange={(event) => update({ outputVariable: event.target.value })}
              value={data.outputVariable ?? ""}
            />
          </Field>
        </>
      ) : null}

      {data.kind === "human_intervention" ? (
        <>
          <div className="rounded-lg border border-sky-300/25 bg-sky-300/10 px-3 py-2 text-xs leading-5 text-sky-50">
            运行到这里会暂停流水线，等待用户在运行面板提交文本后继续。
          </div>
          <Field label="提示文案（支持 {{变量}}）">
            <textarea
              className={`${textInputClass()} min-h-32 resize-none leading-6`}
              onChange={(event) => update({ prompt: event.target.value })}
              value={data.prompt ?? ""}
            />
          </Field>
          <Field label="写入变量名">
            <input
              className={textInputClass()}
              onChange={(event) => update({ outputVariable: event.target.value })}
              value={data.outputVariable ?? ""}
            />
          </Field>
        </>
      ) : null}

      {data.kind === "question_classifier" ? (
        <>
          <div className="rounded-lg border border-yellow-300/25 bg-yellow-300/10 px-3 py-2 text-xs leading-5 text-yellow-50">
            默认只按关键词规则分类；LLM 回退关闭时不会产生模型调用。
          </div>
          <Field label="输入文本变量">
            <input
              className={textInputClass()}
              onChange={(event) => update({ inputVariable: event.target.value })}
              value={data.inputVariable ?? ""}
            />
          </Field>
          <Field label="分类规则 JSON">
            <textarea
              className={`${textInputClass()} min-h-36 resize-none font-mono text-xs leading-5`}
              onChange={(event) => update({ categories: event.target.value })}
              placeholder='{"投诉":["差","投诉","退款"],"咨询":["咨询","如何","怎么"]}'
              value={data.categories ?? ""}
            />
          </Field>
          <Field label="输出变量">
            <input
              className={textInputClass()}
              onChange={(event) => update({ outputVariable: event.target.value })}
              value={data.outputVariable ?? ""}
            />
          </Field>
          <Field label="默认类别">
            <input
              className={textInputClass()}
              onChange={(event) => update({ defaultCategory: event.target.value })}
              value={data.defaultCategory ?? ""}
            />
          </Field>
          <Field label="匹配模式">
            <select
              className={textInputClass()}
              onChange={(event) => update({ matchMode: event.target.value })}
              value={data.matchMode ?? "contains_any"}
            >
              <option className="bg-slate-950" value="contains_any">
                任一关键词命中
              </option>
              <option className="bg-slate-950" value="contains_all">
                全部关键词命中
              </option>
            </select>
          </Field>
          <Field label="大小写敏感">
            <select
              className={textInputClass()}
              onChange={(event) => update({ caseSensitive: event.target.value })}
              value={data.caseSensitive ?? "false"}
            >
              <option className="bg-slate-950" value="false">
                否
              </option>
              <option className="bg-slate-950" value="true">
                是
              </option>
            </select>
          </Field>
          <Field label="启用 LLM 回退">
            <select
              className={textInputClass()}
              onChange={(event) => update({ useLlmFallback: event.target.value })}
              value={data.useLlmFallback ?? "false"}
            >
              <option className="bg-slate-950" value="false">
                否
              </option>
              <option className="bg-slate-950" value="true">
                是
              </option>
            </select>
          </Field>
          {data.useLlmFallback === "true" ? (
            <>
              <Field label="回退模型">
                <select
                  className={textInputClass()}
                  onChange={(event) => update({ modelId: event.target.value })}
                  value={data.modelId ?? ""}
                >
                  <option className="bg-slate-950" value="">
                    请选择模型
                  </option>
                  {models.map((model) => (
                    <option
                      className="bg-slate-950"
                      key={model.id}
                      value={model.id}
                    >
                      {model.name}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="LLM 回退提示词（可选，支持 {{变量}}）">
                <textarea
                  className={`${textInputClass()} min-h-28 resize-none leading-6`}
                  onChange={(event) =>
                    update({ llmFallbackPrompt: event.target.value })
                  }
                  placeholder="留空则使用后端默认分类提示词。"
                  value={data.llmFallbackPrompt ?? ""}
                />
              </Field>
            </>
          ) : null}
        </>
      ) : null}

      {data.kind === "agent" ? (
        <>
          <div className="rounded-lg border border-violet-300/25 bg-violet-300/10 px-3 py-2 text-xs leading-5 text-violet-50">
            Agent 节点是实验能力：工具模式会尝试调用已注册 MCP 工具，直接模式只调用模型生成回答。
          </div>
          <Field label="执行模式">
            <select
              className={textInputClass()}
              onChange={(event) => update({ agentMode: event.target.value })}
              value={data.agentMode ?? "tool_first"}
            >
              <option className="bg-slate-950" value="tool_first">
                tool_first：优先规划工具调用
              </option>
              <option className="bg-slate-950" value="direct">
                direct：直接回答
              </option>
            </select>
          </Field>
          <Field label="任务指令（支持 {{变量}}）">
            <textarea
              className={`${textInputClass()} min-h-36 resize-none leading-6`}
              onChange={(event) => update({ instruction: event.target.value })}
              placeholder="例如：请基于 {{user_input}} 制定处理计划。"
              value={data.instruction ?? ""}
            />
          </Field>
          <Field label="调用模型">
            <select
              className={textInputClass()}
              onChange={(event) => update({ modelId: event.target.value })}
              value={data.modelId ?? ""}
            >
              <option className="bg-slate-950" value="">
                请选择模型
              </option>
              {models.map((model) => (
                <option
                  className="bg-slate-950 text-white"
                  key={model.id}
                  value={model.id}
                >
                  {model.name}
                </option>
              ))}
            </select>
          </Field>
          {data.agentMode !== "direct" ? (
            <>
              <Field label="允许工具名（逗号分隔，留空代表全部已注册工具）">
                <input
                  className={textInputClass()}
                  onChange={(event) => update({ toolNames: event.target.value })}
                  placeholder={
                    registryTools.length
                      ? registryTools.map((tool) => tool.name).slice(0, 3).join(", ")
                      : "先在 MCP 页面连接工具 Server"
                  }
                  value={data.toolNames ?? ""}
                />
              </Field>
              <Field label="最大工具循环次数">
                <input
                  className={textInputClass()}
                  inputMode="numeric"
                  max={20}
                  min={1}
                  onChange={(event) =>
                    update({ maxIterations: event.target.value })
                  }
                  type="number"
                  value={data.maxIterations ?? "5"}
                />
              </Field>
            </>
          ) : null}
          <Field label="Temperature">
            <input
              className={textInputClass()}
              max={2}
              min={0}
              onChange={(event) => update({ temperature: event.target.value })}
              step={0.1}
              type="number"
              value={data.temperature ?? "0.7"}
            />
          </Field>
          <Field label="补充提示词（可选，支持 {{变量}}）">
            <textarea
              className={`${textInputClass()} min-h-24 resize-none leading-6`}
              onChange={(event) => update({ promptSuffix: event.target.value })}
              placeholder="可加入输出格式、语气或额外约束。"
              value={data.promptSuffix ?? ""}
            />
          </Field>
          <Field label="输出变量">
            <input
              className={textInputClass()}
              onChange={(event) => update({ outputVariable: event.target.value })}
              value={data.outputVariable ?? ""}
            />
          </Field>
        </>
      ) : null}

      {data.kind === "workflow_agent" ? (
        <>
          <div className="rounded-lg border border-cyan-300/25 bg-cyan-300/10 px-3 py-2 text-xs leading-5 text-cyan-50">
            该节点会以角色提示词调用模型执行一个工作流步骤；启用 MCP 工具时会复用 runtime toolset、权限策略和审计。
          </div>
          <Field label="智能体名称">
            <input
              className={textInputClass()}
              onChange={(event) => update({ agentName: event.target.value })}
              value={data.agentName ?? ""}
            />
          </Field>
          <Field label="调用模型">
            <select
              className={textInputClass()}
              onChange={(event) => update({ modelId: event.target.value })}
              value={data.modelId ?? ""}
            >
              <option className="bg-slate-950" value="">
                请选择模型
              </option>
              {models.map((model) => (
                <option
                  className="bg-slate-950 text-white"
                  key={model.id}
                  value={model.id}
                >
                  {model.name}
                </option>
              ))}
            </select>
          </Field>
          <Field label="角色提示词（支持 {{变量}}）">
            <textarea
              className={`${textInputClass()} min-h-32 resize-none leading-6`}
              onChange={(event) => update({ rolePrompt: event.target.value })}
              value={data.rolePrompt ?? ""}
            />
          </Field>
          <Field label="任务输入（支持 {{变量}}）">
            <textarea
              className={`${textInputClass()} min-h-32 resize-none leading-6`}
              onChange={(event) => update({ taskInput: event.target.value })}
              value={data.taskInput ?? ""}
            />
          </Field>
          <Field label="工具模式">
            <select
              className={textInputClass()}
              onChange={(event) => update({ toolMode: event.target.value })}
              value={data.toolMode ?? "none"}
            >
              <option className="bg-slate-950" value="none">
                none：直接调用模型
              </option>
              <option className="bg-slate-950" value="mcp_tools">
                mcp_tools：允许调用 MCP 工具
              </option>
            </select>
          </Field>
          {data.toolMode === "mcp_tools" ? (
            <>
              <Field label="允许工具名（逗号分隔，留空代表全部已注册工具）">
                <input
                  className={textInputClass()}
                  onChange={(event) => update({ toolNames: event.target.value })}
                  placeholder={
                    registryTools.length
                      ? registryTools.map((tool) => tool.name).slice(0, 3).join(", ")
                      : "先在 MCP 页面连接工具 Server"
                  }
                  value={data.toolNames ?? ""}
                />
              </Field>
              <Field label="最大工具循环次数">
                <input
                  className={textInputClass()}
                  inputMode="numeric"
                  max={20}
                  min={1}
                  onChange={(event) =>
                    update({ maxIterations: event.target.value })
                  }
                  type="number"
                  value={data.maxIterations ?? "5"}
                />
              </Field>
            </>
          ) : null}
          <Field label="补充提示词（可选，支持 {{变量}}）">
            <textarea
              className={`${textInputClass()} min-h-24 resize-none leading-6`}
              onChange={(event) => update({ promptSuffix: event.target.value })}
              placeholder="可加入输出格式、语气或额外约束。"
              value={data.promptSuffix ?? ""}
            />
          </Field>
          <Field label="输出变量">
            <input
              className={textInputClass()}
              onChange={(event) => update({ outputVariable: event.target.value })}
              value={data.outputVariable ?? ""}
            />
          </Field>
        </>
      ) : null}

      {data.kind === "agent_task" ? (
        <>
          <div className="rounded-lg border border-violet-300/25 bg-violet-300/10 px-3 py-2 text-xs leading-5 text-violet-50">
            该节点会在运行时创建 Agent Task，并将新任务的 task_id 写入输出变量；当前不做真实多 Agent 调度。
          </div>
          <Field label="任务标题（支持 {{变量}}）">
            <input
              className={textInputClass()}
              onChange={(event) => update({ taskTitle: event.target.value })}
              value={data.taskTitle ?? ""}
            />
          </Field>
          <Field label="任务输入（支持 {{变量}}）">
            <textarea
              className={`${textInputClass()} min-h-32 resize-none leading-6`}
              onChange={(event) => update({ taskInput: event.target.value })}
              value={data.taskInput ?? ""}
            />
          </Field>
          <Field label="指派智能体">
            <input
              className={textInputClass()}
              onChange={(event) => update({ assignedAgent: event.target.value })}
              value={data.assignedAgent ?? ""}
            />
          </Field>
          <Field label="输出变量">
            <input
              className={textInputClass()}
              onChange={(event) => update({ outputVariable: event.target.value })}
              value={data.outputVariable ?? ""}
            />
          </Field>
        </>
      ) : null}

      {data.kind === "agent_handoff" ? (
        <>
          <div className="rounded-lg border border-purple-300/25 bg-purple-300/10 px-3 py-2 text-xs leading-5 text-purple-50">
            该节点会读取已有 Agent Task 的 task_id，并创建一条 Handoff 记录；当前只登记移交，不做真实调度。
          </div>
          <Field label="任务 ID 变量">
            <input
              className={textInputClass()}
              onChange={(event) => update({ taskIdVariable: event.target.value })}
              value={data.taskIdVariable ?? ""}
            />
          </Field>
          <Field label="来源智能体">
            <input
              className={textInputClass()}
              onChange={(event) => update({ sourceAgent: event.target.value })}
              value={data.sourceAgent ?? ""}
            />
          </Field>
          <Field label="目标智能体">
            <input
              className={textInputClass()}
              onChange={(event) => update({ targetAgent: event.target.value })}
              value={data.targetAgent ?? ""}
            />
          </Field>
          <Field label="移交理由（支持 {{变量}}）">
            <textarea
              className={`${textInputClass()} min-h-28 resize-none leading-6`}
              onChange={(event) => update({ reason: event.target.value })}
              value={data.reason ?? ""}
            />
          </Field>
          <Field label="输出变量">
            <input
              className={textInputClass()}
              onChange={(event) => update({ outputVariable: event.target.value })}
              value={data.outputVariable ?? ""}
            />
          </Field>
        </>
      ) : null}

      {data.kind === "handoff_router" ? (
        <>
          <div className="rounded-lg border border-fuchsia-300/25 bg-fuchsia-300/10 px-3 py-2 text-xs leading-5 text-fuchsia-50">
            读取上游智能体输出，创建 AgentTask 并投递一条 pending Handoff；目标 Agent 仍需在 Inbox 中人工接受和完成。
          </div>
          <Field label="来源变量">
            <input
              className={textInputClass()}
              onChange={(event) => update({ sourceVariable: event.target.value })}
              value={data.sourceVariable ?? ""}
            />
          </Field>
          <Field label="任务标题（支持 {{变量}}）">
            <input
              className={textInputClass()}
              onChange={(event) => update({ taskTitle: event.target.value })}
              value={data.taskTitle ?? ""}
            />
          </Field>
          <Field label="来源智能体">
            <input
              className={textInputClass()}
              onChange={(event) => update({ sourceAgent: event.target.value })}
              value={data.sourceAgent ?? ""}
            />
          </Field>
          <Field label="目标智能体">
            <input
              className={textInputClass()}
              onChange={(event) => update({ targetAgent: event.target.value })}
              value={data.targetAgent ?? ""}
            />
          </Field>
          <Field label="移交理由模板（支持 {{变量}}）">
            <textarea
              className={`${textInputClass()} min-h-28 resize-none leading-6`}
              onChange={(event) => update({ reasonTemplate: event.target.value })}
              value={data.reasonTemplate ?? ""}
            />
          </Field>
          <Field label="输出变量">
            <input
              className={textInputClass()}
              onChange={(event) => update({ outputVariable: event.target.value })}
              value={data.outputVariable ?? ""}
            />
          </Field>
        </>
      ) : null}

      {data.kind === "mcp_tool" ? (
        <>
          <div className="rounded-lg border border-emerald-300/25 bg-emerald-300/10 px-3 py-2 text-xs leading-5 text-emerald-50">
            先在 MCP 工具采购页连接 Server，工具会自动进入全局注册表。
          </div>
          <Field label="MCP 工具">
            <select
              className={textInputClass()}
              onChange={(event) => update({ toolName: event.target.value })}
              value={data.toolName ?? ""}
            >
              <option className="bg-slate-950" value="">
                {registryTools.length ? "请选择工具" : "暂无已注册工具"}
              </option>
              {registryTools.map((tool) => (
                <option className="bg-slate-950" key={tool.name} value={tool.name}>
                  {tool.name}
                </option>
              ))}
            </select>
            {registryToolsError ? (
              <p className="mt-2 text-xs text-rose-200">{registryToolsError}</p>
            ) : null}
          </Field>
          <Field label="参数 JSON（支持 {{变量}}）">
            <textarea
              className={`${textInputClass()} min-h-32 resize-none font-mono text-xs leading-5`}
              onChange={(event) => update({ argumentsJson: event.target.value })}
              placeholder='{"url":"{{user_input}}"}'
              value={data.argumentsJson ?? "{}"}
            />
          </Field>
          <Field label="输出变量">
            <input
              className={textInputClass()}
              onChange={(event) => update({ outputVariable: event.target.value })}
              value={data.outputVariable ?? ""}
            />
          </Field>
        </>
      ) : null}

      {data.kind === "time_tool" ? (
        <>
          <Field label="时间操作">
            <select
              className={textInputClass()}
              onChange={(event) => update({ operation: event.target.value })}
              value={data.operation ?? "now_iso"}
            >
              <option className="bg-slate-950" value="now_iso">
                当前时间 ISO
              </option>
              <option className="bg-slate-950" value="now_epoch">
                当前时间戳
              </option>
              <option className="bg-slate-950" value="format">
                按格式输出
              </option>
            </select>
          </Field>
          <Field label="格式字符串">
            <input
              className={textInputClass()}
              disabled={data.operation !== "format"}
              onChange={(event) => update({ formatString: event.target.value })}
              placeholder="%Y-%m-%d %H:%M:%S"
              value={data.formatString ?? ""}
            />
          </Field>
          <Field label="输出变量">
            <input
              className={textInputClass()}
              onChange={(event) => update({ outputVariable: event.target.value })}
              value={data.outputVariable ?? ""}
            />
          </Field>
        </>
      ) : null}

      {data.kind === "http_request" ? (
        <>
          <div className="rounded-lg border border-cyan-300/25 bg-cyan-300/10 px-3 py-2 text-xs leading-5 text-cyan-50">
            安全提示：默认运行器不会真实发起出站请求；管理员开启后才会调用外部 URL。
          </div>
          <Field label="请求方法">
            <select
              className={textInputClass()}
              onChange={(event) =>
                update({ method: event.target.value as HttpRequestMethod })
              }
              value={data.method ?? "GET"}
            >
              <option className="bg-slate-950" value="GET">
                GET
              </option>
              <option className="bg-slate-950" value="POST">
                POST
              </option>
            </select>
          </Field>
          <Field label="URL（支持 {{变量}}）">
            <input
              className={textInputClass()}
              onChange={(event) => update({ url: event.target.value })}
              value={data.url ?? ""}
            />
          </Field>
          <Field label="请求头 JSON（可选）">
            <textarea
              className={`${textInputClass()} min-h-24 resize-none font-mono text-xs leading-5`}
              onChange={(event) => update({ headersJson: event.target.value })}
              placeholder='{"Content-Type":"application/json"}'
              value={data.headersJson ?? ""}
            />
          </Field>
          <Field label="请求正文变量（POST 可选）">
            <input
              className={textInputClass()}
              onChange={(event) => update({ bodyVariable: event.target.value })}
              value={data.bodyVariable ?? ""}
            />
          </Field>
          <Field label="响应输出变量">
            <input
              className={textInputClass()}
              onChange={(event) => update({ outputVariable: event.target.value })}
              value={data.outputVariable ?? ""}
            />
          </Field>
        </>
      ) : null}

      {data.kind === "list_operation" ? (
        <>
          <Field label="输入列表变量">
            <input
              className={textInputClass()}
              onChange={(event) => update({ inputVariable: event.target.value })}
              value={data.inputVariable ?? ""}
            />
          </Field>
          <Field label="列表操作">
            <select
              className={textInputClass()}
              onChange={(event) =>
                update({ operator: event.target.value as ListOperationOperator })
              }
              value={data.operator ?? "length"}
            >
              <option className="bg-slate-950" value="length">
                计算长度
              </option>
              <option className="bg-slate-950" value="join">
                拼接文本
              </option>
              <option className="bg-slate-950" value="first">
                取第一项
              </option>
              <option className="bg-slate-950" value="last">
                取最后一项
              </option>
            </select>
          </Field>
          {data.operator === "join" ? (
            <Field label="拼接分隔符">
              <input
                className={textInputClass()}
                onChange={(event) => update({ joinSeparator: event.target.value })}
                value={data.joinSeparator ?? ""}
              />
            </Field>
          ) : null}
          <Field label="输出变量">
            <input
              className={textInputClass()}
              onChange={(event) => update({ outputVariable: event.target.value })}
              value={data.outputVariable ?? ""}
            />
          </Field>
        </>
      ) : null}

      {data.kind === "iteration" ? (
        <>
          <Field label="输入列表变量">
            <input
              className={textInputClass()}
              onChange={(event) => update({ inputVariable: event.target.value })}
              value={data.inputVariable ?? ""}
            />
          </Field>
          <Field label="单项变量名">
            <input
              className={textInputClass()}
              onChange={(event) =>
                update({ iterationVariable: event.target.value })
              }
              value={data.iterationVariable ?? ""}
            />
          </Field>
          <Field label="单项模板（支持 {{单项变量}}）">
            <textarea
              className={`${textInputClass()} min-h-28 resize-none leading-6`}
              onChange={(event) => update({ itemTemplate: event.target.value })}
              value={data.itemTemplate ?? ""}
            />
          </Field>
          <Field label="输出变量">
            <input
              className={textInputClass()}
              onChange={(event) => update({ outputVariable: event.target.value })}
              value={data.outputVariable ?? ""}
            />
          </Field>
        </>
      ) : null}

      {data.kind === "runtime_middleware" ? (
        <div className="space-y-4">
          <div className="rounded-lg border border-indigo-300/25 bg-indigo-300/10 px-3 py-2 text-xs leading-5 text-indigo-50">
            当前为中间件原型节点：运行时会记录并跳过实际编排，下一轮接入真实 MiddlewarePipeline。
          </div>
          <div className="rounded-lg border border-white/10 bg-white/[0.035] px-3 py-2">
            <p className="text-xs font-semibold text-slate-200">
              {data.runtimeMiddlewareKind ?? "runtime_middleware.unknown"}
            </p>
            <p className="mt-1 text-[11px] leading-5 text-slate-500">
              ID：{data.runtimeMiddlewareId ?? "unknown"}
            </p>
          </div>
          {(data.runtimeMiddlewareFields ?? []).length === 0 ? (
            <p className="rounded-lg border border-dashed border-white/15 bg-white/[0.035] px-3 py-4 text-sm leading-6 text-slate-400">
              此中间件暂无可配置字段。
            </p>
          ) : (
            <>
              <p className="text-xs font-semibold text-slate-300">中间件配置</p>
              {(data.runtimeMiddlewareFields ?? []).map((field) => (
                <Field
                  key={field.name}
                  label={`${field.label}${field.required ? " *" : ""}`}
                >
                  {field.type === "text" ? (
                    <input
                      className={textInputClass()}
                      onChange={(event) =>
                        updateRuntimeMiddlewareConfig(
                          field.name,
                          event.target.value,
                        )
                      }
                      placeholder={field.placeholder}
                      value={runtimeMiddlewareStringValue(
                        runtimeMiddlewareConfig,
                        field,
                      )}
                    />
                  ) : null}

                  {field.type === "textarea" ? (
                    <textarea
                      className={`${textInputClass()} min-h-24 resize-none leading-6`}
                      onChange={(event) =>
                        updateRuntimeMiddlewareConfig(
                          field.name,
                          event.target.value,
                        )
                      }
                      placeholder={field.placeholder}
                      rows={field.rows ?? 3}
                      value={runtimeMiddlewareStringValue(
                        runtimeMiddlewareConfig,
                        field,
                      )}
                    />
                  ) : null}

                  {field.type === "boolean" ? (
                    <label className="flex items-start gap-3 rounded-lg border border-white/10 bg-white/[0.045] px-3 py-2 text-sm text-slate-200">
                      <input
                        checked={runtimeMiddlewareBooleanValue(
                          runtimeMiddlewareConfig,
                          field,
                        )}
                        className="mt-1 h-4 w-4 rounded border-white/20 bg-slate-950 text-brand-300"
                        onChange={(event) =>
                          updateRuntimeMiddlewareConfig(
                            field.name,
                            event.target.checked,
                          )
                        }
                        type="checkbox"
                      />
                      <span className="leading-6">
                        {field.description ?? field.label}
                      </span>
                    </label>
                  ) : null}

                  {field.type === "number" ? (
                    <input
                      className={textInputClass()}
                      max={field.maxValue ?? field.max_value}
                      min={field.minValue ?? field.min_value}
                      onChange={(event) =>
                        updateRuntimeMiddlewareConfig(
                          field.name,
                          event.target.value === ""
                            ? ""
                            : Number(event.target.value),
                        )
                      }
                      placeholder={field.placeholder}
                      type="number"
                      value={runtimeMiddlewareStringValue(
                        runtimeMiddlewareConfig,
                        field,
                      )}
                    />
                  ) : null}

                  {field.type === "select" ? (
                    <select
                      className={textInputClass()}
                      onChange={(event) =>
                        updateRuntimeMiddlewareConfig(
                          field.name,
                          event.target.value,
                        )
                      }
                      value={runtimeMiddlewareStringValue(
                        runtimeMiddlewareConfig,
                        field,
                      )}
                    >
                      <option className="bg-slate-950" value="">
                        请选择
                      </option>
                      {(field.options ?? []).map((option) => (
                        <option
                          className="bg-slate-950"
                          key={option}
                          value={option}
                        >
                          {option}
                        </option>
                      ))}
                    </select>
                  ) : null}

                  {field.type === "json" ? (
                    <textarea
                      className={`${textInputClass()} min-h-28 resize-none font-mono text-xs leading-5`}
                      onChange={(event) =>
                        updateRuntimeMiddlewareConfig(
                          field.name,
                          event.target.value,
                        )
                      }
                      placeholder={field.placeholder ?? '{"key":"value"}'}
                      rows={field.rows ?? 4}
                      value={runtimeMiddlewareStringValue(
                        runtimeMiddlewareConfig,
                        field,
                      )}
                    />
                  ) : null}

                  {field.description && field.type !== "boolean" ? (
                    <p className="mt-2 text-xs leading-5 text-slate-500">
                      {field.description}
                    </p>
                  ) : null}
                </Field>
              ))}
            </>
          )}
        </div>
      ) : null}

      {data.kind === "output" ? (
        <Field label="最终输出变量">
          <input
            className={textInputClass()}
            onChange={(event) => update({ outputVariable: event.target.value })}
            value={data.outputVariable ?? ""}
          />
        </Field>
      ) : null}
    </div>
  );
}

interface WorkflowCanvasProps {
  workflowId: string;
}

type WorkflowWorkspaceTab = "config" | "run";

function WorkflowCanvas({ workflowId }: WorkflowCanvasProps) {
  const loadedDefinition = useMemo(() => loadDefinition(workflowId), [workflowId]);
  const [title, setTitle] = useState(loadedDefinition.title);
  const [nodes, setNodes, onNodesChange] = useNodesState<WorkflowNode>(
    loadedDefinition.nodes,
  );
  const [edges, setEdges, onEdgesChange] = useEdgesState<WorkflowEdge>(
    loadedDefinition.edges,
  );
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [selectedEdgeId, setSelectedEdgeId] = useState<string | null>(null);
  const [saveNotice, setSaveNotice] = useState("");
  const [isNodePaletteOpen, setIsNodePaletteOpen] = useState(false);
  const [workspaceTab, setWorkspaceTab] =
    useState<WorkflowWorkspaceTab>("config");
  const { screenToFlowPosition } = useReactFlow();

  const definition = useMemo<WorkflowDefinition>(
    () => ({
      id: workflowId,
      title,
      nodes,
      edges,
      updatedAt: new Date().toISOString(),
    }),
    [edges, nodes, title, workflowId],
  );

  const selectedNode = useMemo(
    () => nodes.find((node) => node.id === selectedNodeId) ?? null,
    [nodes, selectedNodeId],
  );

  const renderedEdges = useMemo(
    () =>
      edges.map((edge) =>
        edge.id === selectedEdgeId
          ? {
              ...edge,
              className: `${edge.className ?? ""} modelmirror-workflow-edge-selected`.trim(),
              style: {
                ...edge.style,
                stroke: "#fb923c",
                strokeWidth: 3,
              },
            }
          : edge,
      ),
    [edges, selectedEdgeId],
  );

  const handleConnect = useCallback(
    (connection: Connection) => {
      setEdges((currentEdges) =>
        addEdge(
          {
            ...connection,
            animated: true,
            className: "modelmirror-workflow-edge",
          },
          currentEdges,
        ),
      );
    },
    [setEdges],
  );

  const handleNodesChange = useCallback(
    (changes: NodeChange<WorkflowNode>[]) => {
      onNodesChange(changes);
    },
    [onNodesChange],
  );

  const handleEdgesChange = useCallback(
    (changes: EdgeChange<WorkflowEdge>[]) => {
      onEdgesChange(changes);
      if (
        selectedEdgeId &&
        changes.some((change) => change.type === "remove" && change.id === selectedEdgeId)
      ) {
        setSelectedEdgeId(null);
      }
    },
    [onEdgesChange, selectedEdgeId],
  );

  const deleteSelectedEdge = useCallback(() => {
    if (!selectedEdgeId) return;
    setEdges((currentEdges) =>
      currentEdges.filter((edge) => edge.id !== selectedEdgeId),
    );
    setSelectedEdgeId(null);
  }, [selectedEdgeId, setEdges]);

  function updateNodeData(nodeId: string, patch: Partial<WorkflowNodeData>) {
    setNodes((currentNodes) =>
      currentNodes.map((node) =>
        node.id === nodeId
          ? {
              ...node,
              data: {
                ...node.data,
                ...patch,
              },
            }
          : node,
      ),
    );
  }

  function saveWorkflow() {
    const savedDefinition = {
      ...definition,
      updatedAt: new Date().toISOString(),
    };
    saveStoredWorkflow(savedDefinition);
    setSaveNotice("已保存到本地草稿箱");
    window.setTimeout(() => setSaveNotice(""), 1800);
  }

  function onDrop(event: React.DragEvent<HTMLDivElement>) {
    event.preventDefault();
    const position = screenToFlowPosition({
      x: event.clientX,
      y: event.clientY,
    });

    const runtimeMiddlewareRaw = event.dataTransfer.getData(
      "application/modelmirror-runtime-middleware",
    );
    const runtimeMiddlewarePayload = runtimeMiddlewareRaw
      ? parseRuntimeMiddlewarePayload(runtimeMiddlewareRaw)
      : null;
    if (runtimeMiddlewarePayload) {
      const nextNode = createNode(
        "runtime_middleware",
        position.x,
        position.y,
        runtimeMiddlewarePayload,
      );
      setNodes((currentNodes) => [...currentNodes, nextNode]);
      setSelectedNodeId(nextNode.id);
      setIsNodePaletteOpen(false);
      return;
    }

    const rawKind = event.dataTransfer.getData("application/modelmirror-node");
    const fallbackPayload = parseRuntimeMiddlewarePayload(rawKind);
    if (fallbackPayload) {
      const nextNode = createNode(
        "runtime_middleware",
        position.x,
        position.y,
        fallbackPayload,
      );
      setNodes((currentNodes) => [...currentNodes, nextNode]);
      setSelectedNodeId(nextNode.id);
      setIsNodePaletteOpen(false);
      return;
    }

    const kind = rawKind as WorkflowNodeKind;
    if (!kind) return;

    const nextNode = createNode(kind, position.x, position.y);
    setNodes((currentNodes) => [...currentNodes, nextNode]);
    setSelectedNodeId(nextNode.id);
    setIsNodePaletteOpen(false);
  }

  useEffect(() => {
    setSelectedNodeId((current) =>
      current && nodes.some((node) => node.id === current) ? current : null,
    );
  }, [nodes]);

  return (
    <div className="grid min-h-[calc(100vh-8rem)] gap-5 xl:grid-cols-[minmax(0,1fr)_380px]">
      <aside className="hidden">
        <p className="text-sm font-semibold text-white">工位库</p>
        <p className="mt-1 text-xs leading-5 text-slate-400">
          拖拽节点到画布，像安排招聘会工位一样搭建 AI 流水线。
        </p>
        <div className="mt-4">
          <NodePalette />
        </div>
      </aside>

      <section className="relative min-w-0 rounded-lg border border-white/10 bg-ink-950/80 shadow-prism">
        <div className="flex flex-col gap-3 border-b border-white/10 bg-surface-900/90 p-4 lg:flex-row lg:items-center lg:justify-between">
          <div className="min-w-0">
            <input
              className="w-full bg-transparent text-xl font-semibold text-white outline-none"
              onChange={(event) => setTitle(event.target.value)}
              value={title}
            />
            <p className="mt-1 text-sm text-slate-400">
              线性 + 条件分支 MVP，支持本地保存和后端流式试运行。
            </p>
          </div>
          <div className="relative flex flex-wrap items-center gap-2">
            <button
              className="rounded-full border border-hire-300/30 bg-hire-300/10 px-4 py-2 text-sm font-semibold text-hire-100 transition hover:border-hire-200/50 hover:bg-hire-300/20"
              onClick={() => setIsNodePaletteOpen((current) => !current)}
              type="button"
            >
              节点库
            </button>
            {isNodePaletteOpen ? (
              <div className="absolute right-0 top-full z-30 mt-3 max-h-[72vh] w-[min(22rem,calc(100vw-2rem))] overflow-y-auto rounded-lg border border-white/10 bg-surface-900/95 p-4 shadow-2xl shadow-ink-950/50 backdrop-blur">
                <NodePalette />
              </div>
            ) : null}
            {saveNotice ? (
              <span className="rounded-full border border-emerald-300/25 bg-emerald-300/10 px-3 py-1.5 text-xs font-semibold text-emerald-100">
                {saveNotice}
              </span>
            ) : null}
            <button
              className="rounded-full border border-white/10 bg-white/[0.06] px-4 py-2 text-sm font-semibold text-slate-100 transition hover:border-hire-300/40 hover:bg-hire-300/10 hover:text-hire-100"
              onClick={saveWorkflow}
              type="button"
            >
              保存草稿
            </button>
          </div>
        </div>

        <div
          className="h-[640px] min-h-[520px] overflow-hidden rounded-b-lg"
          onDragOver={(event) => {
            event.preventDefault();
            event.dataTransfer.dropEffect = "move";
          }}
          onDrop={onDrop}
        >
          <ReactFlow
            edges={renderedEdges}
            fitView
            nodeTypes={nodeTypes}
            nodes={nodes}
            onConnect={handleConnect}
            onEdgeClick={(event, edge) => {
              event.stopPropagation();
              setSelectedNodeId(null);
              setSelectedEdgeId(edge.id);
            }}
            onEdgesChange={handleEdgesChange}
            onNodeClick={(_, node) => {
              setSelectedEdgeId(null);
              setSelectedNodeId(node.id);
            }}
            onNodesChange={handleNodesChange}
            onPaneClick={() => {
              setSelectedEdgeId(null);
              setSelectedNodeId(null);
            }}
          >
            <Background
              color="rgba(253, 186, 116, 0.22)"
              gap={24}
              variant={BackgroundVariant.Dots}
            />
            <Controls className="modelmirror-flow-controls" />
            {selectedEdgeId ? (
              <Panel position="bottom-left">
                <button
                  className="mb-16 rounded-full border border-rose-300/35 bg-rose-400/15 px-3 py-1.5 text-xs font-semibold text-rose-100 shadow-lg shadow-rose-950/30 transition hover:bg-rose-400/25"
                  onClick={deleteSelectedEdge}
                  type="button"
                >
                  × 删除连线
                </button>
              </Panel>
            ) : null}
            <MiniMap
              maskColor="rgba(6, 9, 22, 0.68)"
              nodeColor={() => "rgba(251, 146, 60, 0.9)"}
              pannable
              zoomable
            />
          </ReactFlow>
        </div>
      </section>

      <aside className="surface-panel flex min-h-[520px] flex-col rounded-lg p-4">
        <div className="flex items-start justify-between gap-3 border-b border-white/10 pb-3">
          <div>
            <p className="text-sm font-semibold text-white">工作台</p>
            <p className="mt-1 text-xs leading-5 text-slate-400">
              在同一侧栏内切换节点配置与试运行，减少页面纵向滚动。
            </p>
          </div>
          <div className="flex shrink-0 rounded-full border border-white/10 bg-white/[0.04] p-1">
            <button
              className={`rounded-full px-3 py-1.5 text-xs font-semibold transition ${
                workspaceTab === "config"
                  ? "bg-hire-300 text-ink-950"
                  : "text-slate-400 hover:text-slate-100"
              }`}
              onClick={() => setWorkspaceTab("config")}
              type="button"
            >
              配置
            </button>
            <button
              className={`rounded-full px-3 py-1.5 text-xs font-semibold transition ${
                workspaceTab === "run"
                  ? "bg-hire-300 text-ink-950"
                  : "text-slate-400 hover:text-slate-100"
              }`}
              onClick={() => setWorkspaceTab("run")}
              type="button"
            >
              运行
            </button>
          </div>
        </div>

        <section
          className={
            workspaceTab === "config"
              ? "min-h-0 flex-1 overflow-y-auto pt-4"
              : "hidden"
          }
        >
          <p className="text-sm font-semibold text-white">工位配置</p>
          <p className="mt-1 text-xs leading-5 text-slate-400">
            节点配置会立即写入画布，下次运行直接生效。
          </p>
          <div className="mt-4">
            <NodeConfig node={selectedNode} onChange={updateNodeData} />
          </div>
        </section>

        <div
          className={
            workspaceTab === "run"
              ? "min-h-0 flex flex-1 flex-col pt-4"
              : "hidden"
          }
        >
          <WorkflowRun
            definition={definition}
            embedded
            onRunStart={() => setWorkspaceTab("run")}
          />
        </div>
      </aside>
    </div>
  );
}

export default function WorkflowEditor({ workflowId }: WorkflowCanvasProps) {
  return (
    <ReactFlowProvider>
      <WorkflowCanvas workflowId={workflowId} />
    </ReactFlowProvider>
  );
}

