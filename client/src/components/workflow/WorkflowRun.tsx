import { useMemo, useState } from "react";
import {
  type WorkflowDefinition,
  type WorkflowRunEvent,
} from "../../types/workflow";

interface WorkflowRunProps {
  definition: WorkflowDefinition;
}

interface PendingHumanIntervention {
  nodeId: string;
  nodeTitle: string;
  prompt: string;
  outputVariable: string;
}

function serializeWorkflow(definition: WorkflowDefinition) {
  return {
    id: definition.id,
    title: definition.title,
    nodes: definition.nodes.map((node) => ({
      id: node.id,
      type: node.data.kind,
      position: node.position,
      data: node.data,
    })),
    edges: definition.edges.map((edge) => ({
      id: edge.id,
      source: edge.source,
      target: edge.target,
      sourceHandle: edge.sourceHandle,
      targetHandle: edge.targetHandle,
    })),
  };
}

function readSseEvent(eventText: string) {
  return eventText
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter((line) => line.startsWith("data:"))
    .map((line) => line.slice(5).trim())
    .filter(Boolean);
}

export default function WorkflowRun({ definition }: WorkflowRunProps) {
  const [input, setInput] = useState("请帮我把这个需求拆成三步执行计划。");
  const [events, setEvents] = useState<WorkflowRunEvent[]>([]);
  const [isRunning, setIsRunning] = useState(false);
  const [error, setError] = useState("");
  const [taskId, setTaskId] = useState<string | null>(null);
  const [pendingHuman, setPendingHuman] =
    useState<PendingHumanIntervention | null>(null);
  const [humanInput, setHumanInput] = useState("");
  const [isResuming, setIsResuming] = useState(false);

  const finalOutput = useMemo(() => {
    for (let index = events.length - 1; index >= 0; index -= 1) {
      if (events[index].event === "workflow_end") {
        return events[index].final_output ?? "";
      }
    }

    return "";
  }, [events]);

  async function runWorkflow() {
    setEvents([]);
    setError("");
    setTaskId(null);
    setPendingHuman(null);
    setHumanInput("");
    setIsRunning(true);

    try {
      const response = await fetch("/api/workflow/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          workflow: serializeWorkflow(definition),
          inputs: {
            user_input: input,
          },
        }),
      });

      if (!response.ok) {
        const payload = (await response.json().catch(() => null)) as
          | { error?: string; detail?: string }
          | null;
        throw new Error(payload?.error ?? payload?.detail ?? "工作流运行失败。");
      }

      const reader = response.body?.getReader();
      if (!reader) throw new Error("当前浏览器不支持流式运行结果。");

      const decoder = new TextDecoder("utf-8");
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const chunks = buffer.split(/\r?\n\r?\n/);
        buffer = chunks.pop() ?? "";

        for (const chunk of chunks) {
          for (const data of readSseEvent(chunk)) {
            const event = JSON.parse(data) as WorkflowRunEvent;
            handleRunEvent(event);
            if (event.event !== "heartbeat") {
              setEvents((current) => [...current, event]);
            }
          }
        }
      }

      buffer += decoder.decode();
      if (buffer.trim()) {
        for (const data of readSseEvent(buffer)) {
          const event = JSON.parse(data) as WorkflowRunEvent;
          handleRunEvent(event);
          if (event.event !== "heartbeat") {
            setEvents((current) => [...current, event]);
          }
        }
      }
    } catch (runError) {
      setError(runError instanceof Error ? runError.message : "工作流运行失败。");
    } finally {
      setIsRunning(false);
    }
  }

  function handleRunEvent(event: WorkflowRunEvent) {
    if (event.event === "workflow_meta" && event.task_id) {
      setTaskId(event.task_id);
    }
    if (event.event === "human_intervention_pending") {
      setPendingHuman({
        nodeId: event.node_id ?? "",
        nodeTitle: event.node_title ?? "人工介入",
        prompt: event.prompt ?? "请补充人工输入。",
        outputVariable: event.output_variable ?? "human_input",
      });
      setHumanInput("");
    }
    if (event.event === "node_end") {
      setPendingHuman((current) =>
        current?.nodeId === event.node_id ? null : current,
      );
    }
    if (event.event === "workflow_end") {
      setPendingHuman(null);
      setHumanInput("");
    }
  }

  async function resumeWorkflow() {
    if (!taskId || !pendingHuman) return;
    setError("");
    setIsResuming(true);

    try {
      const response = await fetch(`/api/workflow/run/${taskId}/resume`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          input_text: humanInput,
          node_id: pendingHuman.nodeId,
        }),
      });
      if (!response.ok) {
        const payload = (await response.json().catch(() => null)) as
          | { error?: string; detail?: string }
          | null;
        throw new Error(payload?.error ?? payload?.detail ?? "人工输入提交失败。");
      }
    } catch (resumeError) {
      setError(
        resumeError instanceof Error ? resumeError.message : "人工输入提交失败。",
      );
    } finally {
      setIsResuming(false);
    }
  }

  return (
    <aside className="surface-panel flex min-h-0 flex-col rounded-lg">
      <div className="border-b border-white/10 p-4">
        <p className="text-sm font-semibold text-white">流水线试运行</p>
        <p className="mt-1 text-xs leading-5 text-slate-400">
          输入一份任务，观察每个工位的产出。MVP 会按线性和条件分支执行。
        </p>
      </div>

      <div className="space-y-3 p-4">
        <label className="block">
          <span className="text-xs font-semibold text-slate-300">
            user_input
          </span>
          <textarea
            className="mt-2 min-h-28 w-full resize-none rounded-lg border border-white/10 bg-white/[0.055] px-3 py-2 text-sm leading-6 text-white outline-none transition placeholder:text-slate-500 focus:border-brand-300/50 focus:ring-4 focus:ring-brand-300/10"
            onChange={(event) => setInput(event.target.value)}
            value={input}
          />
        </label>

        <button
          className="w-full rounded-full bg-hire-300 px-4 py-2.5 text-sm font-semibold text-ink-950 transition hover:bg-hire-200 active:scale-[0.98] disabled:cursor-not-allowed disabled:bg-white/10 disabled:text-slate-500"
          disabled={isRunning}
          onClick={() => void runWorkflow()}
          type="button"
        >
          {isRunning ? "流水线运行中" : "运行工作流"}
        </button>
      </div>

      {pendingHuman ? (
        <div className="mx-4 mb-3 rounded-lg border border-sky-300/30 bg-sky-300/10 p-3 text-sky-50">
          <div className="flex items-center justify-between gap-3">
            <p className="text-sm font-semibold">{pendingHuman.nodeTitle}</p>
            <span className="rounded-full border border-sky-200/25 bg-sky-200/10 px-2 py-0.5 text-[11px] text-sky-100">
              等待人工输入
            </span>
          </div>
          <p className="mt-2 whitespace-pre-wrap text-xs leading-5 text-sky-100">
            {pendingHuman.prompt}
          </p>
          <p className="mt-2 text-[11px] text-sky-200/80">
            写入变量：{pendingHuman.outputVariable}
          </p>
          <textarea
            className="mt-3 min-h-24 w-full resize-none rounded-lg border border-sky-200/25 bg-slate-950/50 px-3 py-2 text-sm leading-6 text-white outline-none transition placeholder:text-slate-500 focus:border-sky-200/60 focus:ring-4 focus:ring-sky-300/10"
            onChange={(event) => setHumanInput(event.target.value)}
            placeholder="输入人工补充内容..."
            value={humanInput}
          />
          <button
            className="mt-3 w-full rounded-full bg-sky-200 px-4 py-2 text-sm font-semibold text-slate-950 transition hover:bg-sky-100 active:scale-[0.98] disabled:cursor-not-allowed disabled:bg-white/10 disabled:text-slate-500"
            disabled={!taskId || isResuming}
            onClick={() => void resumeWorkflow()}
            type="button"
          >
            {isResuming ? "提交中..." : "提交并继续"}
          </button>
        </div>
      ) : null}

      {error ? (
        <div className="mx-4 rounded-lg border border-rose-300/25 bg-rose-300/10 px-3 py-2 text-sm text-rose-100">
          {error}
        </div>
      ) : null}

      <div className="min-h-0 flex-1 overflow-y-auto p-4">
        <div className="space-y-2">
          {events.length === 0 ? (
            <div className="rounded-lg border border-dashed border-white/15 bg-white/[0.035] px-4 py-8 text-center text-sm leading-6 text-slate-400">
              暂无运行记录。点击“运行工作流”后，这里会像招聘会排班表一样逐项亮起。
            </div>
          ) : (
            events.map((event, index) => (
              <div
                className="rounded-lg border border-white/10 bg-white/[0.045] px-3 py-2"
                key={`${event.event}-${event.node_id ?? "workflow"}-${index}`}
              >
                <div className="flex items-center justify-between gap-3">
                  <span className="text-xs font-semibold text-slate-200">
                    {event.node_title ?? "工作流"}
                  </span>
                  <span className="rounded-full border border-white/10 bg-white/[0.055] px-2 py-0.5 text-[11px] text-slate-400">
                    {event.event}
                  </span>
                </div>
                {event.output || event.final_output || event.message || event.prompt ? (
                  <p className="mt-2 whitespace-pre-wrap text-xs leading-5 text-slate-300">
                    {event.output ?? event.final_output ?? event.message ?? event.prompt}
                  </p>
                ) : null}
              </div>
            ))
          )}
        </div>
      </div>

      {finalOutput ? (
        <div className="border-t border-white/10 p-4">
          <p className="text-xs font-semibold text-hire-100">最终交付</p>
          <p className="mt-2 max-h-44 overflow-y-auto whitespace-pre-wrap rounded-lg border border-hire-300/25 bg-hire-300/10 p-3 text-sm leading-6 text-hire-50">
            {finalOutput}
          </p>
        </div>
      ) : null}
    </aside>
  );
}
