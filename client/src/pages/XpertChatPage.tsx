import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import PageContainer from "../components/PageContainer";
import {
  type XpertConversationMessage,
  type XpertDefinition,
} from "../types/xpert";
import { getXpert } from "../utils/xpertApi";

interface XpertRunEvent {
  event: string;
  task_id?: string;
  run_id?: string;
  node_id?: string;
  node_title?: string;
  node_type?: string;
  output?: string;
  final_output?: string;
  message?: string;
  xpert_id?: string;
  xpert_version?: number;
}

interface RuntimeRunSummary {
  run_id: string;
  run_type: string;
  status: string;
  title: string;
  source_id: string | null;
  parent_run_id: string | null;
  metadata: Record<string, unknown>;
  error: string | null;
}

interface RuntimeCheckpoint {
  checkpoint_id: string;
  event_type: string;
  title: string;
  summary: string;
  severity: string;
  created_at: number;
}

interface ToolAuditRecord {
  record_id: string;
  tool_name: string;
  status: string;
  duration_ms: number | null;
  output_length: number | null;
  error: string | null;
}

interface TraceBundle {
  run: RuntimeRunSummary | null;
  childRuns: RuntimeRunSummary[];
  checkpoints: RuntimeCheckpoint[];
  childCheckpoints: Record<string, RuntimeCheckpoint[]>;
  audits: ToolAuditRecord[];
}

async function responseError(response: Response) {
  try {
    const payload = (await response.json()) as { detail?: string; error?: string };
    return payload.detail || payload.error || `请求失败：${response.status}`;
  } catch {
    return `请求失败：${response.status}`;
  }
}

function eventSummary(event: XpertRunEvent) {
  if (event.event === "workflow_meta") return "运行已登记";
  if (event.event === "workflow_end") return "最终回答已生成";
  if (event.event === "error") return event.message || "运行失败";
  return event.output || event.message || event.node_title || event.event;
}

function roleCopy(role: XpertConversationMessage["role"]) {
  return role === "user" ? "你" : "Xpert";
}

export default function XpertChatPage() {
  const { xpertId = "" } = useParams();
  const [xpert, setXpert] = useState<XpertDefinition | null>(null);
  const [version, setVersion] = useState<number | null>(null);
  const [messages, setMessages] = useState<XpertConversationMessage[]>([]);
  const [input, setInput] = useState("");
  const [events, setEvents] = useState<XpertRunEvent[]>([]);
  const [runId, setRunId] = useState("");
  const [taskId, setTaskId] = useState("");
  const [trace, setTrace] = useState<TraceBundle | null>(null);
  const [showTrace, setShowTrace] = useState(false);
  const [running, setRunning] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    getXpert(xpertId)
      .then((data) => {
        if (cancelled) return;
        setXpert(data);
        setVersion(data.published_version);
        document.title = `模镜 - ${data.name}`;
      })
      .catch((caught) => {
        if (!cancelled) setError(caught instanceof Error ? caught.message : "Xpert 加载失败");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [xpertId]);

  const publishedVersions = useMemo(
    () => [...(xpert?.versions ?? [])].sort((a, b) => b.version - a.version),
    [xpert],
  );

  async function loadTrace(nextRunId: string, nextTaskId: string) {
    try {
      const [runResponse, checkpointsResponse, childrenResponse, observationResponse] =
        await Promise.all([
          fetch(`/api/runtime/runs/${nextRunId}`),
          fetch(`/api/runtime/runs/${nextRunId}/checkpoints`),
          fetch(`/api/runtime/runs?parent_run_id=${encodeURIComponent(nextRunId)}&limit=50`),
          nextTaskId
            ? fetch(`/api/workflow/runtime-events/${nextTaskId}`)
            : Promise.resolve(null),
        ]);
      const run = runResponse.ok
        ? ((await runResponse.json()) as RuntimeRunSummary)
        : null;
      const checkpoints = checkpointsResponse.ok
        ? ((await checkpointsResponse.json()) as RuntimeCheckpoint[])
        : [];
      const childRuns = childrenResponse.ok
        ? ((await childrenResponse.json()) as RuntimeRunSummary[])
        : [];
      const childCheckpointEntries = await Promise.all(
        childRuns.map(async (child) => {
          const response = await fetch(`/api/runtime/runs/${child.run_id}/checkpoints`);
          return [
            child.run_id,
            response.ok ? ((await response.json()) as RuntimeCheckpoint[]) : [],
          ] as const;
        }),
      );
      const observation = observationResponse?.ok
        ? ((await observationResponse.json()) as { tool_audit_records?: ToolAuditRecord[] })
        : null;
      setTrace({
        run,
        childRuns,
        checkpoints,
        childCheckpoints: Object.fromEntries(childCheckpointEntries),
        audits: observation?.tool_audit_records ?? [],
      });
    } catch {
      setTrace(null);
    }
  }

  async function sendMessage(messageOverride?: string) {
    const message = (messageOverride ?? input).trim();
    if (!message || !xpert || !version || running) return;

    const history = messages.slice(-20);
    setMessages((current) => [...current, { role: "user", content: message }]);
    setInput("");
    setEvents([]);
    setTrace(null);
    setRunId("");
    setTaskId("");
    setRunning(true);
    setError("");

    try {
      const response = await fetch(`/api/xperts/${xpert.id}/run`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message, messages: history, version }),
      });
      if (!response.ok) throw new Error(await responseError(response));
      if (!response.body) throw new Error("浏览器未收到流式响应。 ");

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let finalOutput = "";
      let nextRunId = "";
      let nextTaskId = "";

      const processBlock = (block: string) => {
        for (const line of block.split(/\r?\n/)) {
          if (!line.startsWith("data:")) continue;
          const raw = line.slice(5).trim();
          if (!raw) continue;
          const event = JSON.parse(raw) as XpertRunEvent;
          setEvents((current) => [...current.slice(-79), event]);
          if (event.run_id) {
            nextRunId = event.run_id;
            setRunId(event.run_id);
          }
          if (event.task_id) {
            nextTaskId = event.task_id;
            setTaskId(event.task_id);
          }
          if (event.event === "workflow_end") {
            finalOutput = event.final_output || "";
          }
          if (event.event === "error") {
            throw new Error(event.message || "Xpert 运行失败");
          }
        }
      };

      while (true) {
        const { done, value } = await reader.read();
        buffer += decoder.decode(value, { stream: !done });
        let match = buffer.match(/\r?\n\r?\n/);
        while (match?.index !== undefined) {
          processBlock(buffer.slice(0, match.index));
          buffer = buffer.slice(match.index + match[0].length);
          match = buffer.match(/\r?\n\r?\n/);
        }
        if (done) break;
      }
      if (buffer.trim()) processBlock(buffer);
      setMessages((current) => [
        ...current,
        { role: "assistant", content: finalOutput || "运行完成，但没有返回文本输出。" },
      ]);
      if (nextRunId) await loadTrace(nextRunId, nextTaskId);
    } catch (caught) {
      const messageText = caught instanceof Error ? caught.message : "Xpert 运行失败";
      setError(messageText);
      setMessages((current) => [...current, { role: "assistant", content: `运行失败：${messageText}` }]);
    } finally {
      setRunning(false);
    }
  }

  if (loading) {
    return (
      <PageContainer activeResource="agents" maxWidthClassName="max-w-[1560px]">
        <div className="h-[70vh] animate-pulse rounded-lg border border-white/10 bg-white/[0.04]" />
      </PageContainer>
    );
  }

  if (!xpert) {
    return (
      <PageContainer activeResource="agents">
        <div className="rounded-lg border border-rose-300/25 bg-rose-300/10 p-5 text-sm text-rose-100">{error || "Xpert 不存在。"}</div>
      </PageContainer>
    );
  }

  if (xpert.status !== "published" || !xpert.published_version || !version) {
    return (
      <PageContainer activeResource="agents">
        <div className="rounded-lg border border-white/10 bg-white/[0.04] p-8 text-center">
          <h1 className="text-xl font-semibold text-white">{xpert.name} 尚未发布</h1>
          <p className="mt-2 text-sm text-slate-400">先完成发布预检并生成一个不可变版本，再从聊天入口运行。</p>
          <Link className="mt-4 inline-flex rounded-full bg-hire-300 px-4 py-2 text-sm font-semibold text-ink-950" to={`/agents/studio/${xpert.id}`}>进入 Studio</Link>
        </div>
      </PageContainer>
    );
  }

  return (
    <PageContainer activeResource="agents" maxWidthClassName="max-w-[1560px]">
      <div className="grid min-h-[calc(100vh-9rem)] gap-5 xl:grid-cols-[minmax(0,1fr)_400px]">
        <section className="flex min-h-[680px] min-w-0 flex-col overflow-hidden rounded-lg border border-white/10 bg-ink-950/76">
          <header className="flex flex-col gap-3 border-b border-white/10 p-4 sm:flex-row sm:items-center sm:justify-between">
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-hire-300/25 bg-hire-300/10 text-xs font-bold text-hire-100">XP</span>
                <div className="min-w-0">
                  <h1 className="truncate text-base font-semibold text-white">{xpert.name}</h1>
                  <p className="truncate text-xs text-slate-500">/{xpert.slug}</p>
                </div>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <select className="h-9 rounded-lg border border-white/10 bg-white/[0.055] px-3 text-xs text-white outline-none" onChange={(event) => setVersion(Number(event.target.value))} value={version}>
                {publishedVersions.map((item) => <option className="bg-ink-950" key={item.version} value={item.version}>v{item.version} · revision {item.draft_revision}</option>)}
              </select>
              <Link className="rounded-full border border-white/10 bg-white/[0.04] px-3 py-2 text-xs font-semibold text-slate-300" to={`/agents/studio/${xpert.id}`}>编辑</Link>
            </div>
          </header>

          <div className="min-h-0 flex-1 overflow-y-auto p-4">
            {messages.length === 0 ? (
              <div className="mx-auto max-w-2xl py-10 text-center">
                <h2 className="text-xl font-semibold text-white">开始与 {xpert.name} 协作</h2>
                <p className="mt-2 text-sm leading-6 text-slate-400">{xpert.description || "这个 Xpert 将运行已发布的工作流版本。"}</p>
                {xpert.starters.length > 0 ? (
                  <div className="mt-6 grid gap-2 sm:grid-cols-2">
                    {xpert.starters.map((starter) => (
                      <button className="rounded-lg border border-white/10 bg-white/[0.04] p-3 text-left text-sm leading-5 text-slate-300 transition hover:border-hire-300/35 hover:bg-hire-300/10 hover:text-hire-100" key={starter} onClick={() => void sendMessage(starter)} type="button">{starter}</button>
                    ))}
                  </div>
                ) : null}
              </div>
            ) : (
              <div className="space-y-4">
                {messages.map((message, index) => (
                  <article className={`max-w-[86%] rounded-lg border p-3 ${message.role === "user" ? "ml-auto border-hire-300/25 bg-hire-300/10" : "border-white/10 bg-white/[0.045]"}`} key={`${message.role}-${index}`}>
                    <p className="text-[10px] font-semibold uppercase text-slate-500">{roleCopy(message.role)}</p>
                    <p className="mt-2 whitespace-pre-wrap text-sm leading-6 text-slate-100">{message.content}</p>
                  </article>
                ))}
                {running ? (
                  <div className="max-w-[86%] rounded-lg border border-white/10 bg-white/[0.04] p-3 text-sm text-slate-400">Xpert 正在执行已发布工作流...</div>
                ) : null}
              </div>
            )}
          </div>

          <footer className="border-t border-white/10 p-4">
            {error ? <p className="mb-3 rounded-lg border border-rose-300/25 bg-rose-300/10 px-3 py-2 text-xs text-rose-100">{error}</p> : null}
            <div className="flex items-end gap-2">
              <textarea className="min-h-12 flex-1 resize-none rounded-lg border border-white/10 bg-white/[0.055] px-3 py-3 text-sm leading-6 text-white outline-none focus:border-hire-300/60" disabled={running} onChange={(event) => setInput(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); void sendMessage(); } }} placeholder="输入任务，Enter 发送，Shift+Enter 换行" rows={2} value={input} />
              <button className="h-12 rounded-lg bg-hire-300 px-5 text-sm font-semibold text-ink-950 transition hover:bg-hire-200 disabled:cursor-not-allowed disabled:opacity-50" disabled={running || !input.trim()} onClick={() => void sendMessage()} type="button">{running ? "执行中" : "发送"}</button>
            </div>
          </footer>
        </section>

        <aside className="surface-panel flex min-h-[680px] flex-col rounded-lg p-4">
          <div className="flex items-start justify-between gap-3 border-b border-white/10 pb-3">
            <div>
              <h2 className="text-sm font-semibold text-white">运行轨迹</h2>
              <p className="mt-1 text-xs leading-5 text-slate-400">SSE 节点事件、RunRegistry、checkpoint 与工具审计摘要。</p>
            </div>
            <button className="rounded-full border border-white/10 bg-white/[0.04] px-3 py-1.5 text-xs font-semibold text-slate-300" onClick={() => setShowTrace((current) => !current)} type="button">{showTrace ? "收起" : "展开"}</button>
          </div>

          <dl className="mt-4 grid grid-cols-2 gap-2 text-xs">
            <div className="rounded-lg border border-white/10 bg-white/[0.04] p-3"><dt className="text-slate-500">版本</dt><dd className="mt-1 font-semibold text-white">v{version}</dd></div>
            <div className="rounded-lg border border-white/10 bg-white/[0.04] p-3"><dt className="text-slate-500">状态</dt><dd className="mt-1 font-semibold text-white">{running ? "运行中" : trace?.run?.status ?? "待运行"}</dd></div>
            <div className="col-span-2 rounded-lg border border-white/10 bg-white/[0.04] p-3"><dt className="text-slate-500">Run ID</dt><dd className="mt-1 break-all font-mono text-[11px] text-slate-300">{runId || "-"}</dd></div>
          </dl>

          {showTrace ? (
            <div className="mt-4 min-h-0 flex-1 space-y-4 overflow-y-auto">
              <section>
                <div className="flex items-center justify-between"><h3 className="text-xs font-semibold text-white">即时事件</h3><span className="text-[10px] text-slate-500">{events.length}</span></div>
                <div className="mt-2 space-y-2">
                  {events.length > 0 ? events.slice(-30).map((event, index) => (
                    <div className="rounded-lg border border-white/10 bg-ink-950/55 px-3 py-2" key={`${event.event}-${event.node_id ?? index}-${index}`}>
                      <div className="flex items-center justify-between gap-2"><span className="text-[11px] font-semibold text-hire-100">{event.node_title || event.event}</span><span className="text-[10px] text-slate-600">{event.node_type || event.event}</span></div>
                      <p className="mt-1 line-clamp-3 text-[11px] leading-4 text-slate-400">{eventSummary(event)}</p>
                    </div>
                  )) : <p className="rounded-lg border border-dashed border-white/10 p-3 text-center text-xs text-slate-500">运行后显示节点事件</p>}
                </div>
              </section>

              <section>
                <div className="flex items-center justify-between"><h3 className="text-xs font-semibold text-white">Checkpoint</h3><span className="text-[10px] text-slate-500">{trace?.checkpoints.length ?? 0}</span></div>
                <div className="mt-2 space-y-2">
                  {(trace?.checkpoints ?? []).slice(0, 20).map((checkpoint) => (
                    <div className="rounded-lg border border-white/10 bg-white/[0.035] px-3 py-2" key={checkpoint.checkpoint_id}>
                      <div className="flex items-center justify-between gap-2"><span className="text-[11px] font-semibold text-white">{checkpoint.title}</span><span className="text-[10px] text-slate-500">{checkpoint.severity}</span></div>
                      <p className="mt-1 line-clamp-2 text-[11px] text-slate-400">{checkpoint.summary || checkpoint.event_type}</p>
                    </div>
                  ))}
                </div>
              </section>

              <section>
                <div className="flex items-center justify-between"><h3 className="text-xs font-semibold text-white">节点子 Run</h3><span className="text-[10px] text-slate-500">{trace?.childRuns.length ?? 0}</span></div>
                <div className="mt-2 space-y-2">
                  {(trace?.childRuns ?? []).map((run) => {
                    const checkpoints = trace?.childCheckpoints[run.run_id] ?? [];
                    return (
                      <div className="rounded-lg border border-white/10 bg-white/[0.035] px-3 py-2" key={run.run_id}>
                        <div className="flex items-center justify-between gap-2"><span className="text-[11px] font-semibold text-white">{run.title}</span><span className="text-[10px] text-slate-500">{run.status}</span></div>
                        <p className="mt-1 text-[10px] text-slate-500">{run.run_type} · {checkpoints.length} checkpoints</p>
                        {checkpoints.slice(0, 3).map((checkpoint) => (
                          <p className="mt-1 line-clamp-1 text-[10px] text-slate-400" key={checkpoint.checkpoint_id}>{checkpoint.event_type}: {checkpoint.summary || checkpoint.title}</p>
                        ))}
                      </div>
                    );
                  })}
                </div>
              </section>

              <section>
                <div className="flex items-center justify-between"><h3 className="text-xs font-semibold text-white">工具审计</h3><span className="text-[10px] text-slate-500">{trace?.audits.length ?? 0}</span></div>
                <div className="mt-2 space-y-2">
                  {(trace?.audits ?? []).slice(0, 20).map((audit) => (
                    <div className="rounded-lg border border-white/10 bg-white/[0.035] px-3 py-2" key={audit.record_id}>
                      <div className="flex items-center justify-between gap-2"><span className="text-[11px] font-semibold text-white">{audit.tool_name}</span><span className="text-[10px] text-slate-500">{audit.status}</span></div>
                      <p className="mt-1 text-[10px] text-slate-500">{audit.duration_ms != null ? `${audit.duration_ms.toFixed(0)}ms` : "-"} · {audit.output_length ?? 0} chars</p>
                    </div>
                  ))}
                </div>
              </section>
            </div>
          ) : (
            <p className="mt-4 rounded-lg border border-dashed border-white/10 p-4 text-center text-xs leading-5 text-slate-500">展开后查看最近一次运行的完整摘要。不会展示完整 prompt、工具输出或密钥。</p>
          )}
          {taskId ? <p className="mt-3 break-all text-[10px] text-slate-600">task: {taskId}</p> : null}
        </aside>
      </div>
    </PageContainer>
  );
}
