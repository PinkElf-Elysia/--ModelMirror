import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import PageContainer from "../components/PageContainer";
import {
  type XpertConversationMessage,
  type XpertConversation,
  type XpertDefinition,
  type XpertFileAsset,
  type XpertMemoryCandidate,
  type XpertMemoryRecord,
  type XpertSummary,
} from "../types/xpert";
import { createGoal } from "../utils/goalApi";
import {
  archiveXpertFile,
  archiveXpertMemory,
  createXpertConversation,
  createXpertMemory,
  decideXpertMemoryCandidate,
  getXpert,
  getXpertConversation,
  listXpertConversations,
  listXpertFiles,
  listXpertMemories,
  listXpertMemoryCandidates,
  listXperts,
  uploadXpertFile,
} from "../utils/xpertApi";

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

interface KnowledgeBaseSummary {
  id: string;
  name: string;
  document_count: number;
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
  const navigate = useNavigate();
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
  const [showGoalComposer, setShowGoalComposer] = useState(false);
  const [goalTitle, setGoalTitle] = useState("");
  const [goalObjective, setGoalObjective] = useState("");
  const [plannerXpertId, setPlannerXpertId] = useState("");
  const [publishedXperts, setPublishedXperts] = useState<XpertSummary[]>([]);
  const [creatingGoal, setCreatingGoal] = useState(false);
  const [conversations, setConversations] = useState<XpertConversation[]>([]);
  const [conversationId, setConversationId] = useState("");
  const [files, setFiles] = useState<XpertFileAsset[]>([]);
  const [selectedFileIds, setSelectedFileIds] = useState<string[]>([]);
  const [memories, setMemories] = useState<XpertMemoryRecord[]>([]);
  const [memoryCandidates, setMemoryCandidates] = useState<XpertMemoryCandidate[]>([]);
  const [contextLoading, setContextLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [showContext, setShowContext] = useState(false);
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBaseSummary[]>([]);
  const [knowledgeTargetId, setKnowledgeTargetId] = useState("");
  const [promotingFiles, setPromotingFiles] = useState(false);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

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

  useEffect(() => {
    listXperts({ status: "published", limit: 200 })
      .then((payload) => setPublishedXperts(payload.items))
      .catch(() => setPublishedXperts([]));
  }, []);

  useEffect(() => {
    fetch("/api/rag/knowledge_bases")
      .then(async (response) => {
        if (!response.ok) throw new Error(await responseError(response));
        return response.json() as Promise<{ knowledge_bases: KnowledgeBaseSummary[] }>;
      })
      .then((payload) => {
        setKnowledgeBases(payload.knowledge_bases);
        setKnowledgeTargetId((current) => current || payload.knowledge_bases[0]?.id || "");
      })
      .catch(() => setKnowledgeBases([]));
  }, []);

  useEffect(() => {
    if (!xpert) return;
    let cancelled = false;
    setContextLoading(true);
    listXpertConversations(xpert.id)
      .then(async (payload) => {
        if (cancelled) return;
        let active = payload.items[0];
        if (!active) active = await createXpertConversation(xpert.id);
        if (cancelled) return;
        setConversations(active ? [active, ...payload.items.filter((item) => item.conversation_id !== active.conversation_id)] : payload.items);
        await selectConversation(active.conversation_id, xpert.id, cancelled);
      })
      .catch((caught) => {
        if (!cancelled) setError(caught instanceof Error ? caught.message : "\u4f1a\u8bdd\u52a0\u8f7d\u5931\u8d25");
      })
      .finally(() => {
        if (!cancelled) setContextLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [xpert?.id]);

  const publishedVersions = useMemo(
    () => [...(xpert?.versions ?? [])].sort((a, b) => b.version - a.version),
    [xpert],
  );

  async function selectConversation(
    nextConversationId: string,
    selectedXpertId = xpert?.id,
    cancelled = false,
  ) {
    if (!selectedXpertId || !nextConversationId) return;
    const [conversation, filePayload, memoryPayload, candidatePayload] = await Promise.all([
      getXpertConversation(selectedXpertId, nextConversationId),
      listXpertFiles(selectedXpertId, nextConversationId),
      listXpertMemories(selectedXpertId, nextConversationId),
      listXpertMemoryCandidates(selectedXpertId, nextConversationId),
    ]);
    if (cancelled) return;
    setConversationId(nextConversationId);
    setMessages(conversation.messages ?? []);
    setFiles(filePayload.items);
    setSelectedFileIds(filePayload.items.slice(0, 5).map((item) => item.asset_id));
    setMemories(memoryPayload.items);
    setMemoryCandidates(candidatePayload.items);
  }

  async function refreshContext() {
    if (!xpert || !conversationId) return;
    const [conversationPayload, filePayload, memoryPayload, candidatePayload] = await Promise.all([
      listXpertConversations(xpert.id),
      listXpertFiles(xpert.id, conversationId),
      listXpertMemories(xpert.id, conversationId),
      listXpertMemoryCandidates(xpert.id, conversationId),
    ]);
    setConversations(conversationPayload.items);
    setFiles(filePayload.items);
    setSelectedFileIds((current) =>
      current.filter((assetId) => filePayload.items.some((item) => item.asset_id === assetId)),
    );
    setMemories(memoryPayload.items);
    setMemoryCandidates(candidatePayload.items);
  }

  async function startConversation() {
    if (!xpert || running) return;
    const created = await createXpertConversation(xpert.id);
    setConversations((current) => [created, ...current]);
    await selectConversation(created.conversation_id);
  }

  async function handleFileUpload(file: File) {
    if (!xpert || !conversationId) return;
    setUploading(true);
    setError("");
    try {
      const uploaded = await uploadXpertFile(xpert.id, conversationId, file);
      await refreshContext();
      setSelectedFileIds((current) => [...current, uploaded.asset_id].slice(-5));
      setShowContext(true);
      setShowTrace(false);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "\u6587\u4ef6\u4e0a\u4f20\u5931\u8d25");
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  }

  async function promoteSelectedFilesToKnowledge() {
    if (!xpert || !conversationId || !knowledgeTargetId || selectedFileIds.length === 0) return;
    setPromotingFiles(true);
    setError("");
    try {
      const draftResponse = await fetch(
        `/api/rag/pipeline/draft?kb_id=${encodeURIComponent(knowledgeTargetId)}`,
      );
      if (!draftResponse.ok) throw new Error(await responseError(draftResponse));
      const draft = (await draftResponse.json()) as { version: number };
      const response = await fetch(`/api/rag/pipeline/draft/${knowledgeTargetId}/execute`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          draft_version: draft.version,
          source_document_ids: [],
          xpert_file_refs: selectedFileIds.map((assetId) => ({
            xpert_id: xpert.id,
            conversation_id: conversationId,
            asset_id: assetId,
          })),
        }),
      });
      if (!response.ok) throw new Error(await responseError(response));
      const job = (await response.json()) as { job_id: string };
      navigate(
        `/rag?kb_id=${encodeURIComponent(knowledgeTargetId)}&job_id=${encodeURIComponent(job.job_id)}`,
      );
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "附件加入知识库失败");
    } finally {
      setPromotingFiles(false);
    }
  }

  async function rememberMessage(message: XpertConversationMessage) {
    if (!xpert || !conversationId) return;
    await createXpertMemory(xpert.id, {
      content: message.content,
      scope: "xpert",
      conversation_id: conversationId,
      source_type: "user_action",
      source_id: message.message_id,
    });
    await refreshContext();
    setShowContext(true);
    setShowTrace(false);
  }

  async function decideCandidate(candidateId: string, action: "approve" | "reject") {
    if (!xpert) return;
    await decideXpertMemoryCandidate(xpert.id, candidateId, action);
    await refreshContext();
  }

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
    if (!message || !xpert || !version || running || !conversationId) return;

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
        body: JSON.stringify({
          message,
          messages: history,
          version,
          conversation_id: conversationId,
          file_asset_ids: selectedFileIds,
        }),
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
      window.setTimeout(() => void refreshContext(), 800);
    } catch (caught) {
      const messageText = caught instanceof Error ? caught.message : "Xpert 运行失败";
      setError(messageText);
      setMessages((current) => [...current, { role: "assistant", content: `运行失败：${messageText}` }]);
    } finally {
      setRunning(false);
    }
  }

  function openGoalComposer() {
    const lastUserMessage = [...messages].reverse().find((message) => message.role === "user");
    const objective = lastUserMessage?.content || input.trim() || xpert?.starters[0] || "";
    setGoalTitle(objective ? `长期目标：${objective.slice(0, 36)}` : `长期目标：${xpert?.name ?? "Xpert"}`);
    setGoalObjective(objective);
    setPlannerXpertId(xpert?.id ?? publishedXperts[0]?.id ?? "");
    setShowGoalComposer(true);
  }

  async function createLongGoal() {
    if (!xpert || !goalTitle.trim() || !goalObjective.trim() || !plannerXpertId) return;
    setCreatingGoal(true);
    setError("");
    try {
      const created = await createGoal({
        title: goalTitle.trim(),
        objective: goalObjective.trim(),
        planner_xpert_id: plannerXpertId,
        source_xpert_id: xpert.id,
        source_conversation_id: conversationId,
        file_asset_ids: selectedFileIds,
        messages: messages.slice(-20),
        max_parallel: 2,
      });
      navigate(`/agents/goals/${created.goal_id}`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "长期 Goal 创建失败");
    } finally {
      setCreatingGoal(false);
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
            <div className="flex flex-wrap items-center justify-end gap-2">
              <select
                className="h-9 max-w-44 rounded-lg border border-white/10 bg-white/[0.055] px-3 text-xs text-white outline-none"
                disabled={contextLoading || running}
                onChange={(event) => void selectConversation(event.target.value)}
                value={conversationId}
              >
                {conversations.map((item) => (
                  <option className="bg-ink-950" key={item.conversation_id} value={item.conversation_id}>
                    {item.title}
                  </option>
                ))}
              </select>
              <button
                className="inline-flex h-9 items-center rounded-lg border border-white/10 bg-white/[0.04] px-3 text-xs font-semibold text-slate-300 hover:bg-white/[0.08]"
                disabled={running}
                onClick={() => void startConversation()}
                type="button"
              >
                {"+ \u65b0\u4f1a\u8bdd"}
              </button>
              <button
                className="inline-flex h-9 items-center gap-2 rounded-lg border border-cyan-300/25 bg-cyan-300/10 px-3 text-xs font-semibold text-cyan-100 transition hover:border-cyan-200/45 hover:bg-cyan-300/15"
                onClick={openGoalComposer}
                type="button"
              >
                <span aria-hidden="true" className="text-[10px] font-bold">GL</span>转为长期目标
              </button>
              <select className="h-9 rounded-lg border border-white/10 bg-white/[0.055] px-3 text-xs text-white outline-none" onChange={(event) => setVersion(Number(event.target.value))} value={version}>
                {publishedVersions.map((item) => <option className="bg-ink-950" key={item.version} value={item.version}>v{item.version} · revision {item.draft_revision}</option>)}
              </select>
              <Link className="rounded-full border border-white/10 bg-white/[0.04] px-3 py-2 text-xs font-semibold text-slate-300" to={`/agents/studio/${xpert.id}`}>编辑</Link>
            </div>
          </header>

          {showGoalComposer ? (
            <section className="border-b border-cyan-300/20 bg-cyan-300/[0.055] p-4">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <h2 className="text-sm font-semibold text-white">创建长期 Goal</h2>
                  <p className="mt-1 text-xs leading-5 text-slate-400">Planner 先生成可编辑计划，审核后才开始执行。</p>
                </div>
                <button aria-label="关闭长期目标创建区" className="rounded-md p-1.5 text-base text-slate-400 hover:bg-white/10 hover:text-white" onClick={() => setShowGoalComposer(false)} type="button">×</button>
              </div>
              <div className="mt-3 grid gap-3 lg:grid-cols-2">
                <label className="text-xs font-semibold text-slate-400">标题<input className="mt-1 h-9 w-full rounded-lg border border-white/10 bg-ink-950/50 px-3 text-sm text-white outline-none focus:border-cyan-300/40" onChange={(event) => setGoalTitle(event.target.value)} value={goalTitle} /></label>
                <label className="text-xs font-semibold text-slate-400">Planner Xpert<select className="mt-1 h-9 w-full rounded-lg border border-white/10 bg-ink-950/50 px-3 text-sm text-white outline-none" onChange={(event) => setPlannerXpertId(event.target.value)} value={plannerXpertId}>{publishedXperts.map((item) => <option className="bg-ink-950" key={item.id} value={item.id}>{item.name} / v{item.published_version}</option>)}</select></label>
              </div>
              <label className="mt-3 block text-xs font-semibold text-slate-400">目标<textarea className="mt-1 min-h-24 w-full resize-y rounded-lg border border-white/10 bg-ink-950/50 p-3 text-sm leading-6 text-white outline-none focus:border-cyan-300/40" onChange={(event) => setGoalObjective(event.target.value)} value={goalObjective} /></label>
              <div className="mt-3 flex justify-end"><button className="h-9 rounded-lg bg-cyan-300 px-4 text-sm font-semibold text-ink-950 disabled:cursor-not-allowed disabled:opacity-50" disabled={creatingGoal || !goalTitle.trim() || !goalObjective.trim() || !plannerXpertId} onClick={() => void createLongGoal()} type="button">{creatingGoal ? "创建中..." : "创建并规划"}</button></div>
            </section>
          ) : null}

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
                    <button
                      className="mt-2 text-[10px] font-semibold text-cyan-200/75 transition hover:text-cyan-100"
                      onClick={() => void rememberMessage(message)}
                      type="button"
                    >
                      {"\u8bb0\u4f4f\u8fd9\u6761"}
                    </button>
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
            {selectedFileIds.length > 0 ? (
              <div className="mb-2 flex flex-wrap gap-2">
                {files.filter((file) => selectedFileIds.includes(file.asset_id)).map((file) => (
                  <button
                    className="rounded-md border border-cyan-300/20 bg-cyan-300/10 px-2 py-1 text-[10px] text-cyan-100"
                    key={file.asset_id}
                    onClick={() => setSelectedFileIds((current) => current.filter((item) => item !== file.asset_id))}
                    type="button"
                  >
                    {file.filename} {"\u00d7"}
                  </button>
                ))}
              </div>
            ) : null}
            <div className="flex items-end gap-2">
              <input
                accept=".txt,.md,.markdown,.pdf"
                className="hidden"
                onChange={(event) => {
                  const file = event.target.files?.[0];
                  if (file) void handleFileUpload(file);
                }}
                ref={fileInputRef}
                type="file"
              />
              <button
                className="h-12 rounded-lg border border-white/10 bg-white/[0.04] px-3 text-xs font-semibold text-slate-300 hover:bg-white/[0.08] disabled:opacity-50"
                disabled={running || uploading || !conversationId}
                onClick={() => fileInputRef.current?.click()}
                type="button"
              >
                {uploading ? "\u4e0a\u4f20\u4e2d..." : "\u9644\u4ef6"}
              </button>
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

          <button
            className="mt-3 w-full rounded-lg border border-cyan-300/20 bg-cyan-300/10 px-3 py-2 text-xs font-semibold text-cyan-100"
            onClick={() => { setShowContext((current) => !current); setShowTrace(false); }}
            type="button"
          >
            {showContext ? "\u6536\u8d77\u6587\u4ef6\u4e0e\u8bb0\u5fc6" : "\u6587\u4ef6\u4e0e\u8bb0\u5fc6"}
          </button>

          {showContext ? (
            <div className="mt-4 min-h-0 flex-1 space-y-5 overflow-y-auto">
              <section>
                <div className="flex items-center justify-between">
                  <h3 className="text-xs font-semibold text-white">{"\u4f1a\u8bdd\u9644\u4ef6"}</h3>
                  <span className="text-[10px] text-slate-500">{files.length} / 20</span>
                </div>
                <p className="mt-1 text-[10px] leading-4 text-slate-500">{"\u6bcf\u6b21\u6700\u591a\u9009\u62e9 5 \u4e2a\u6587\u4ef6\u8fdb\u5165 Xpert \u4e0a\u4e0b\u6587\u3002"}</p>
                <div className="mt-2 space-y-2">
                  {files.length ? files.map((file) => (
                    <div className="flex items-start gap-2 rounded-lg border border-white/10 bg-white/[0.035] p-2.5" key={file.asset_id}>
                      <input
                        checked={selectedFileIds.includes(file.asset_id)}
                        className="mt-1"
                        onChange={(event) => setSelectedFileIds((current) => {
                          if (!event.target.checked) return current.filter((item) => item !== file.asset_id);
                          if (current.includes(file.asset_id) || current.length >= 5) return current;
                          return [...current, file.asset_id];
                        })}
                        type="checkbox"
                      />
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-[11px] font-semibold text-white">{file.filename}</p>
                        <p className="mt-1 text-[10px] text-slate-500">{file.character_count} chars / {(file.size_bytes / 1024).toFixed(1)} KB</p>
                      </div>
                      <button className="text-[10px] text-rose-200" onClick={() => xpert && void archiveXpertFile(xpert.id, conversationId, file.asset_id).then(refreshContext)} type="button">{"\u5f52\u6863"}</button>
                    </div>
                  )) : <p className="rounded-lg border border-dashed border-white/10 p-3 text-center text-xs text-slate-500">{"\u5c1a\u672a\u4e0a\u4f20\u9644\u4ef6"}</p>}
                </div>
                <div className="mt-3 border-t border-white/10 pt-3">
                  <div className="text-[11px] font-semibold text-white">加入知识库</div>
                  <p className="mt-1 text-[10px] leading-4 text-slate-500">
                    仅发送当前勾选附件，生成候选索引后到知识库页面预览并人工激活。
                  </p>
                  <div className="mt-2 flex gap-2">
                    <select
                      className="min-w-0 flex-1 rounded-md border border-white/10 bg-ink-950/60 px-2 py-1.5 text-[11px] text-white outline-none"
                      onChange={(event) => setKnowledgeTargetId(event.target.value)}
                      value={knowledgeTargetId}
                    >
                      {knowledgeBases.length === 0 ? (
                        <option value="">暂无知识库</option>
                      ) : knowledgeBases.map((kb) => (
                        <option className="bg-ink-950" key={kb.id} value={kb.id}>
                          {kb.name} · {kb.document_count} 文档
                        </option>
                      ))}
                    </select>
                    <button
                      className="inline-flex shrink-0 items-center gap-1.5 rounded-md bg-hire-300 px-2.5 py-1.5 text-[11px] font-semibold text-ink-950 transition hover:bg-hire-200 disabled:cursor-not-allowed disabled:opacity-50"
                      disabled={promotingFiles || selectedFileIds.length === 0 || !knowledgeTargetId}
                      onClick={() => void promoteSelectedFilesToKnowledge()}
                      type="button"
                    >
                      {promotingFiles ? "提交中..." : "创建候选"}
                    </button>
                  </div>
                </div>
              </section>

              <section>
                <div className="flex items-center justify-between"><h3 className="text-xs font-semibold text-white">{"\u5f85\u786e\u8ba4\u8bb0\u5fc6"}</h3><span className="text-[10px] text-slate-500">{memoryCandidates.length}</span></div>
                <div className="mt-2 space-y-2">
                  {memoryCandidates.map((candidate) => (
                    <div className="rounded-lg border border-amber-300/20 bg-amber-300/[0.06] p-2.5" key={candidate.candidate_id}>
                      <p className="line-clamp-4 text-[11px] leading-5 text-slate-200">{candidate.content}</p>
                      <div className="mt-2 flex justify-end gap-2">
                        <button className="text-[10px] text-slate-400" onClick={() => void decideCandidate(candidate.candidate_id, "reject")} type="button">{"\u62d2\u7edd"}</button>
                        <button className="text-[10px] font-semibold text-emerald-200" onClick={() => void decideCandidate(candidate.candidate_id, "approve")} type="button">{"\u6279\u51c6"}</button>
                      </div>
                    </div>
                  ))}
                </div>
              </section>

              <section>
                <div className="flex items-center justify-between"><h3 className="text-xs font-semibold text-white">{"\u5df2\u751f\u6548\u8bb0\u5fc6"}</h3><span className="text-[10px] text-slate-500">{memories.length}</span></div>
                <div className="mt-2 space-y-2">
                  {memories.map((memory) => (
                    <div className="rounded-lg border border-white/10 bg-white/[0.035] p-2.5" key={memory.memory_id}>
                      <div className="flex items-center justify-between gap-2"><span className="text-[10px] font-semibold text-cyan-100">{memory.scope}</span><button className="text-[10px] text-rose-200" onClick={() => xpert && void archiveXpertMemory(xpert.id, memory.memory_id).then(refreshContext)} type="button">{"\u5f52\u6863"}</button></div>
                      <p className="mt-1 line-clamp-4 text-[11px] leading-5 text-slate-300">{memory.content}</p>
                    </div>
                  ))}
                </div>
              </section>
            </div>
          ) : null}

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
