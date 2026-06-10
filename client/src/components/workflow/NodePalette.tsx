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
    kind: "output",
    icon: "📤",
    title: "输出节点",
    description: "收尾交付最终变量，展示运行结果。",
  },
];

export default function NodePalette() {
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
    </div>
  );
}
