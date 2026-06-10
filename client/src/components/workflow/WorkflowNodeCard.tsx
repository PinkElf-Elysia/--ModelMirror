import { Handle, Position, type NodeProps } from "@xyflow/react";
import { type WorkflowNode } from "../../types/workflow";

const nodeMeta = {
  input: {
    icon: "📥",
    label: "输入工位",
    border: "border-emerald-300/40",
    bg: "bg-emerald-300/10",
    text: "text-emerald-100",
  },
  llm: {
    icon: "🤖",
    label: "LLM 工位",
    border: "border-brand-300/40",
    bg: "bg-brand-300/10",
    text: "text-brand-100",
  },
  condition: {
    icon: "🔀",
    label: "分流工位",
    border: "border-amber-300/45",
    bg: "bg-amber-300/10",
    text: "text-amber-100",
  },
  code: {
    icon: "🔧",
    label: "加工工位",
    border: "border-accent-300/40",
    bg: "bg-accent-300/10",
    text: "text-accent-100",
  },
  output: {
    icon: "📤",
    label: "交付工位",
    border: "border-hire-300/45",
    bg: "bg-hire-300/10",
    text: "text-hire-100",
  },
};

function outputName(data: WorkflowNode["data"]) {
  if (data.kind === "input") return data.variableName ?? "user_input";
  if (data.kind === "condition") {
    return `${data.conditionVariable ?? "变量"} ${data.conditionOperator === "equals" ? "等于" : "包含"} ${data.conditionValue ?? "值"}`;
  }
  if (data.kind === "code") return data.codeOutputVariable ?? "code_output";
  if (data.kind === "output") return data.outputVariable ?? "final_output";
  return data.outputVariable ?? "llm_output";
}

export default function WorkflowNodeCard({ data, selected }: NodeProps<WorkflowNode>) {
  const meta = nodeMeta[data.kind];

  return (
    <div
      className={`relative min-w-56 rounded-lg border bg-surface-900/95 p-3 text-slate-100 shadow-prism backdrop-blur-xl transition duration-200 ${
        selected
          ? "border-hire-200/70 ring-4 ring-hire-300/15"
          : meta.border
      }`}
    >
      {data.kind !== "input" ? (
        <Handle
          className="!h-3 !w-3 !border-2 !border-surface-900 !bg-slate-200"
          position={Position.Left}
          type="target"
        />
      ) : null}

      <div className="flex items-start gap-3">
        <span
          className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border ${meta.border} ${meta.bg} text-lg`}
        >
          {meta.icon}
        </span>
        <div className="min-w-0">
          <span
            className={`inline-flex rounded-full border px-2 py-0.5 text-[11px] font-semibold ${meta.border} ${meta.bg} ${meta.text}`}
          >
            {meta.label}
          </span>
          <h3 className="mt-2 line-clamp-2 text-sm font-semibold text-white">
            {data.title}
          </h3>
          <p className="mt-1 line-clamp-2 text-xs leading-5 text-slate-400">
            {data.description}
          </p>
        </div>
      </div>

      <div className="mt-3 rounded-md border border-white/10 bg-white/[0.045] px-2.5 py-2">
        <p className="text-[11px] text-slate-500">变量/判断</p>
        <p className="mt-0.5 truncate text-xs font-semibold text-slate-100">
          {outputName(data)}
        </p>
      </div>

      {data.kind === "condition" ? (
        <>
          <Handle
            className="!h-3 !w-3 !border-2 !border-surface-900 !bg-emerald-300"
            id="true"
            position={Position.Right}
            style={{ top: "38%" }}
            type="source"
          />
          <Handle
            className="!h-3 !w-3 !border-2 !border-surface-900 !bg-rose-300"
            id="false"
            position={Position.Right}
            style={{ top: "68%" }}
            type="source"
          />
          <div className="pointer-events-none absolute -right-12 top-[32%] text-[10px] font-semibold text-emerald-100">
            是
          </div>
          <div className="pointer-events-none absolute -right-12 top-[62%] text-[10px] font-semibold text-rose-100">
            否
          </div>
        </>
      ) : data.kind !== "output" ? (
        <Handle
          className="!h-3 !w-3 !border-2 !border-surface-900 !bg-hire-300"
          position={Position.Right}
          type="source"
        />
      ) : null}
    </div>
  );
}
