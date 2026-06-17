import {
  addEdge,
  Background,
  BackgroundVariant,
  Controls,
  MiniMap,
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
import NodePalette from "./NodePalette";
import WorkflowNodeCard from "./WorkflowNodeCard";
import WorkflowRun from "./WorkflowRun";

const nodeTypes = {
  workflowNode: WorkflowNodeCard,
};

const storagePrefix = "modelmirror-workflow:";

function createNodeData(kind: WorkflowNodeKind): WorkflowNodeData {
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

  return {
    kind,
    title: "最终交付",
    description: "把指定变量作为工作流结果交付。",
    outputVariable: "llm_output",
  };
}

function createNode(kind: WorkflowNodeKind, x: number, y: number): WorkflowNode {
  return {
    id: `${kind}-${Date.now()}-${Math.random().toString(16).slice(2, 7)}`,
    type: "workflowNode",
    position: { x, y },
    data: createNodeData(kind),
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
  const raw = window.localStorage.getItem(`${storagePrefix}${workflowId}`);
  if (!raw) return initialDefinition(workflowId);

  try {
    return JSON.parse(raw) as WorkflowDefinition;
  } catch {
    return initialDefinition(workflowId);
  }
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
  const [saveNotice, setSaveNotice] = useState("");
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
    },
    [onEdgesChange],
  );

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
    window.localStorage.setItem(
      `${storagePrefix}${workflowId}`,
      JSON.stringify(savedDefinition),
    );
    setSaveNotice("已保存到本地草稿箱");
    window.setTimeout(() => setSaveNotice(""), 1800);
  }

  function onDrop(event: React.DragEvent<HTMLDivElement>) {
    event.preventDefault();
    const kind = event.dataTransfer.getData(
      "application/modelmirror-node",
    ) as WorkflowNodeKind;
    if (!kind) return;

    const position = screenToFlowPosition({
      x: event.clientX,
      y: event.clientY,
    });
    const nextNode = createNode(kind, position.x, position.y);
    setNodes((currentNodes) => [...currentNodes, nextNode]);
    setSelectedNodeId(nextNode.id);
  }

  useEffect(() => {
    setSelectedNodeId((current) =>
      current && nodes.some((node) => node.id === current) ? current : null,
    );
  }, [nodes]);

  return (
    <div className="grid min-h-[calc(100vh-8rem)] gap-5 xl:grid-cols-[260px_minmax(0,1fr)_360px]">
      <aside className="surface-panel rounded-lg p-4">
        <p className="text-sm font-semibold text-white">工位库</p>
        <p className="mt-1 text-xs leading-5 text-slate-400">
          拖拽节点到画布，像安排招聘会工位一样搭建 AI 流水线。
        </p>
        <div className="mt-4">
          <NodePalette />
        </div>
      </aside>

      <section className="min-w-0 overflow-hidden rounded-lg border border-white/10 bg-ink-950/80 shadow-prism">
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
          <div className="flex flex-wrap items-center gap-2">
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
          className="h-[640px] min-h-[520px]"
          onDragOver={(event) => {
            event.preventDefault();
            event.dataTransfer.dropEffect = "move";
          }}
          onDrop={onDrop}
        >
          <ReactFlow
            edges={edges}
            fitView
            nodeTypes={nodeTypes}
            nodes={nodes}
            onConnect={handleConnect}
            onEdgesChange={handleEdgesChange}
            onNodeClick={(_, node) => setSelectedNodeId(node.id)}
            onNodesChange={handleNodesChange}
          >
            <Background
              color="rgba(253, 186, 116, 0.22)"
              gap={24}
              variant={BackgroundVariant.Dots}
            />
            <Controls />
            <MiniMap
              maskColor="rgba(6, 9, 22, 0.68)"
              nodeColor={() => "rgba(251, 146, 60, 0.9)"}
              pannable
              zoomable
            />
          </ReactFlow>
        </div>
      </section>

      <aside className="grid min-h-0 gap-5 xl:grid-rows-[minmax(0,1fr)_minmax(360px,0.95fr)]">
        <section className="surface-panel min-h-0 overflow-y-auto rounded-lg p-4">
          <p className="text-sm font-semibold text-white">工位配置</p>
          <p className="mt-1 text-xs leading-5 text-slate-400">
            节点配置会立即写入画布，下次运行直接生效。
          </p>
          <div className="mt-4">
            <NodeConfig node={selectedNode} onChange={updateNodeData} />
          </div>
        </section>

        <WorkflowRun definition={definition} />
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
