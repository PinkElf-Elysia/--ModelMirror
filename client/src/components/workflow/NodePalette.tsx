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
