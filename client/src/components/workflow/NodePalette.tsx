import { useEffect, useState } from "react";

import {
  fetchRuntimeMiddlewareNodes,
  type RuntimeMiddlewareNode,
} from "../../types/runtimeMiddleware";
import { type WorkflowNodeKind } from "../../types/workflow";

interface PaletteItem {
  kind: WorkflowNodeKind;
  icon: string;
  title: string;
  description: string;
}

const paletteItems: PaletteItem[] = [
  {
    kind: "input",
    icon: "📥",
    title: "输入节点",
    description: "定义流水线入口变量，默认 user_input。",
  },
  {
    kind: "llm",
    icon: "🤖",
    title: "LLM 节点",
    description: "安排模型工位处理提示词，可引用 {{变量}}。",
  },
  {
    kind: "condition",
    icon: "🔀",
    title: "条件分支",
    description: "按变量值判断，走“是/否”两条传送带。",
  },
  {
    kind: "code",
    icon: "🔧",
    title: "代码节点",
    description: "只支持安全的内置字符串加工函数。",
  },
  {
    kind: "variable_assign",
    icon: "🪄",
    title: "变量赋值",
    description: "把模板渲染成一个变量，适合整理中间结果。",
  },
  {
    kind: "template_transform",
    icon: "📝",
    title: "模板转换",
    description: "渲染长文本模板，适合生成报告或结构化草稿。",
  },
  {
    kind: "variable_aggregator",
    icon: "🔗",
    title: "变量聚合器",
    description: "把多个变量汇总为文本或 JSON 字符串。",
  },
  {
    kind: "parameter_extractor",
    icon: "🎯",
    title: "参数提取器",
    description: "调用模型从文本中提取字段，输出 JSON 字符串。",
  },
  {
    kind: "knowledge_retrieval",
    icon: "📚",
    title: "知识检索",
    description: "查询本地 RAG 资料库，把相关段落写入变量。",
  },
  {
    kind: "document_extractor",
    icon: "📄",
    title: "文档提取器",
    description: "从受限本地路径提取文本，供后续节点使用。",
  },
  {
    kind: "human_intervention",
    icon: "👤",
    title: "人工介入",
    description: "暂停流水线，等待用户补充文本后再继续执行。",
  },
  {
    kind: "question_classifier",
    icon: "🏷️",
    title: "问题分类器",
    description: "根据关键词规则把输入文本分类为预设类别。可与条件节点串联做分流。",
  },
  {
    kind: "agent",
    icon: "🤖",
    title: "Agent 节点",
    description: "模型驱动的任务执行节点，支持工具循环和直接回答两种模式。",
  },
  {
    kind: "workflow_agent",
    icon: "🧭",
    title: "工作流智能体",
    description: "用角色提示词执行一个模型驱动的 Agent 步骤，并写入输出变量。",
  },
  {
    kind: "agent_task",
    icon: "▣",
    title: "智能体任务",
    description: "创建 Agent Task Runtime 任务，输出 task_id 供后续节点引用。",
  },
  {
    kind: "agent_handoff",
    icon: "⇄",
    title: "智能体移交",
    description: "把 Agent Task 显式移交给另一个智能体，输出 handoff_id。",
  },
  {
    kind: "mcp_tool",
    icon: "🔧",
    title: "MCP Tool",
    description: "调用已连接 MCP Server 暴露的工具，参数支持 {{变量}} 模板。",
  },
  {
    kind: "time_tool",
    icon: "🕒",
    title: "时间工具",
    description: "获取当前时间、时间戳或按格式输出日期文本。",
  },
  {
    kind: "http_request",
    icon: "🌐",
    title: "HTTP 请求",
    description: "调用 GET/POST 接口，把响应文本写入变量。",
  },
  {
    kind: "list_operation",
    icon: "📋",
    title: "列表操作",
    description: "对逗号分隔的列表做长度、拼接、首尾提取。",
  },
  {
    kind: "iteration",
    icon: "🔁",
    title: "迭代处理",
    description: "逐项渲染模板，汇总为一个 JSON 数组字符串。",
  },
  {
    kind: "output",
    icon: "📤",
    title: "输出节点",
    description: "收尾交付最终变量，展示运行结果。",
  },
];

const middlewareIconMap: Record<string, string> = {
  Activity: "〽",
  ClipboardList: "▦",
  MessageSquare: "◇",
  Puzzle: "▣",
  Shield: "◇",
};

function MiddlewareIcon({ icon }: { icon: string }) {
  return <span aria-hidden="true">{middlewareIconMap[icon] ?? "▣"}</span>;
}

export default function NodePalette() {
  const [middlewareNodes, setMiddlewareNodes] = useState<RuntimeMiddlewareNode[]>([]);
  const [middlewareLoading, setMiddlewareLoading] = useState(false);
  const [middlewareError, setMiddlewareError] = useState<string | null>(null);

  useEffect(() => {
    let isMounted = true;
    setMiddlewareLoading(true);
    fetchRuntimeMiddlewareNodes()
      .then((nodes) => {
        if (!isMounted) {
          return;
        }
        setMiddlewareNodes(nodes.filter((node) => node.enabled));
        setMiddlewareError(null);
      })
      .catch((error) => {
        console.error("Failed to load middleware nodes:", error);
        if (!isMounted) {
          return;
        }
        setMiddlewareError("加载中间件节点失败");
      })
      .finally(() => {
        if (isMounted) {
          setMiddlewareLoading(false);
        }
      });

    return () => {
      isMounted = false;
    };
  }, []);

  return (
    <div className="space-y-3">
      {paletteItems.map((item) => (
        <button
          className="group w-full rounded-lg border border-white/10 bg-white/[0.045] p-3 text-left transition duration-200 hover:-translate-y-0.5 hover:border-hire-300/35 hover:bg-hire-300/10"
          draggable
          key={item.kind}
          onDragStart={(event) => {
            event.dataTransfer.setData("application/modelmirror-node", item.kind);
            event.dataTransfer.effectAllowed = "move";
          }}
          type="button"
        >
          <span className="flex items-start gap-3">
            <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-hire-300/25 bg-hire-300/10 text-lg">
              {item.icon}
            </span>
            <span className="min-w-0">
              <span className="block text-sm font-semibold text-white">
                {item.title}
              </span>
              <span className="mt-1 block text-xs leading-5 text-slate-400">
                {item.description}
              </span>
            </span>
          </span>
        </button>
      ))}

      <div className="pt-3">
        <div className="mb-2 flex items-center justify-between">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
            智能体中间件
          </h3>
          {middlewareLoading ? (
            <span className="text-[11px] text-slate-500">加载中...</span>
          ) : null}
        </div>

        {middlewareError ? (
          <p className="rounded-lg border border-amber-300/20 bg-amber-300/10 px-3 py-2 text-xs leading-5 text-amber-100">
            {middlewareError}，原有节点可继续使用。
          </p>
        ) : null}

        {!middlewareError && middlewareNodes.length > 0 ? (
          <div className="space-y-3">
            {middlewareNodes.map((node) => (
              <button
                className="group w-full rounded-lg border border-white/10 bg-white/[0.045] p-3 text-left transition duration-200 hover:-translate-y-0.5 hover:border-hire-300/35 hover:bg-hire-300/10"
                draggable
                key={node.id}
                onDragStart={(event) => {
                  const payload = {
                    kind: "runtime_middleware",
                    runtimeMiddlewareId: node.id,
                    runtimeMiddlewareKind: node.kind,
                    title: node.title,
                    description: node.description,
                    fields: node.fields,
                    metadata: node.metadata ?? {},
                  };
                  const serialized = JSON.stringify(payload);
                  event.dataTransfer.setData("application/modelmirror-node", serialized);
                  event.dataTransfer.setData(
                    "application/modelmirror-runtime-middleware",
                    serialized,
                  );
                  event.dataTransfer.effectAllowed = "move";
                }}
                type="button"
              >
                <span className="flex items-start gap-3">
                  <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-hire-300/25 bg-hire-300/10 text-hire-100">
                    <MiddlewareIcon icon={node.icon} />
                  </span>
                  <span className="min-w-0">
                    <span className="block text-sm font-semibold text-white">
                      {node.title}
                    </span>
                    <span className="mt-1 block text-xs leading-5 text-slate-400">
                      {node.description}
                    </span>
                  </span>
                </span>
              </button>
            ))}
          </div>
        ) : null}
      </div>
    </div>
  );
}
