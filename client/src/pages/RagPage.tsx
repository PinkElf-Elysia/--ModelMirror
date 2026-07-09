import { type DragEvent, useEffect, useMemo, useRef, useState } from "react";
import PageContainer from "../components/PageContainer";

interface KnowledgeBase {
  id: string;
  name: string;
  document_count: number;
  created_at: number;
  updated_at: number;
}

interface KnowledgeBaseListResponse {
  knowledge_bases: KnowledgeBase[];
}

interface RagDocument {
  id: string;
  kb_id: string;
  filename: string;
  size: number;
  chunk_count: number;
  created_at: number;
}

interface DocumentListResponse {
  documents: RagDocument[];
}

interface PipelineAsset {
  file_asset_id: string;
  document_id: string;
  knowledge_base_id: string;
  filename: string;
  size: number;
  extension: string;
  mime_type?: string | null;
  created_at: number;
}

interface PipelineAssetListResponse {
  assets: PipelineAsset[];
  asset_count: number;
}

interface PipelineArtifact {
  artifact_id: string;
  file_asset_id: string;
  document_id: string;
  knowledge_base_id: string;
  title: string;
  chunk_count: number;
  created_at: number;
}

interface PipelineArtifactListResponse {
  artifacts: PipelineArtifact[];
  artifact_count: number;
}

interface PipelineDraftStage {
  id: string;
  kind: string;
  title: string;
  status: string;
  item_count: number;
  summary: string;
  metadata?: Record<string, unknown>;
}

interface PipelineDraftResponse {
  kb_id: string;
  stages: PipelineDraftStage[];
  stage_count: number;
}

const MAX_FILE_BYTES = 10 * 1024 * 1024;
const SUPPORTED_EXTENSIONS = [".txt", ".md", ".markdown", ".pdf"];

function formatDate(timestamp: number) {
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(timestamp * 1000));
}

function formatFileSize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function stageStatusLabel(status: string) {
  if (status === "ready") return "可观测";
  if (status === "empty") return "暂无数据";
  if (status === "planned") return "待接入";
  return status || "未知";
}

function stageStatusClass(status: string) {
  if (status === "ready") return "border-emerald-300/25 bg-emerald-300/10 text-emerald-100";
  if (status === "planned") return "border-amber-300/25 bg-amber-300/10 text-amber-100";
  return "border-white/10 bg-white/[0.06] text-slate-300";
}

async function readError(response: Response) {
  try {
    const data = (await response.json()) as { detail?: string; error?: string };
    return data.detail ?? data.error ?? `请求失败：${response.status}`;
  } catch {
    return `请求失败：${response.status}`;
  }
}

function validateFile(file: File) {
  const lowerName = file.name.toLowerCase();
  const isSupported = SUPPORTED_EXTENSIONS.some((extension) =>
    lowerName.endsWith(extension),
  );
  if (!isSupported) {
    return "仅支持 TXT、Markdown 和 PDF 文档。";
  }
  if (file.size > MAX_FILE_BYTES) {
    return "文件过大，请上传 10MB 以内的文档。";
  }
  return "";
}

export default function RagPage() {
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBase[]>([]);
  const [selectedKbId, setSelectedKbId] = useState("");
  const [documents, setDocuments] = useState<RagDocument[]>([]);
  const [isLoadingKbs, setIsLoadingKbs] = useState(false);
  const [isLoadingDocs, setIsLoadingDocs] = useState(false);
  const [isCreating, setIsCreating] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [newKbName, setNewKbName] = useState("");
  const [isPipelineOpen, setIsPipelineOpen] = useState(false);
  const [isLoadingPipeline, setIsLoadingPipeline] = useState(false);
  const [pipelineError, setPipelineError] = useState("");
  const [pipelineAssets, setPipelineAssets] = useState<PipelineAsset[]>([]);
  const [pipelineArtifacts, setPipelineArtifacts] = useState<PipelineArtifact[]>([]);
  const [pipelineDraft, setPipelineDraft] = useState<PipelineDraftResponse | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const selectedKnowledgeBase = useMemo(
    () => knowledgeBases.find((item) => item.id === selectedKbId) ?? null,
    [knowledgeBases, selectedKbId],
  );

  const pipelineChunkCount = useMemo(
    () => pipelineArtifacts.reduce((total, artifact) => total + artifact.chunk_count, 0),
    [pipelineArtifacts],
  );

  useEffect(() => {
    document.title = "模镜 - 知识库管理";
    void loadKnowledgeBases();
  }, []);

  useEffect(() => {
    if (!selectedKbId) {
      setDocuments([]);
      setPipelineAssets([]);
      setPipelineArtifacts([]);
      setPipelineDraft(null);
      setPipelineError("");
      return;
    }
    void loadDocuments(selectedKbId);
    if (isPipelineOpen) void loadPipeline(selectedKbId);
  }, [isPipelineOpen, selectedKbId]);

  async function loadKnowledgeBases(nextSelectedId?: string) {
    setIsLoadingKbs(true);
    setError("");
    try {
      const response = await fetch("/api/rag/knowledge_bases");
      if (!response.ok) throw new Error(await readError(response));
      const data = (await response.json()) as KnowledgeBaseListResponse;
      setKnowledgeBases(data.knowledge_bases);
      const preferredId =
        nextSelectedId ??
        selectedKbId ??
        data.knowledge_bases[0]?.id ??
        "";
      if (preferredId && data.knowledge_bases.some((item) => item.id === preferredId)) {
        setSelectedKbId(preferredId);
      } else {
        setSelectedKbId(data.knowledge_bases[0]?.id ?? "");
      }
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "知识库列表加载失败。");
    } finally {
      setIsLoadingKbs(false);
    }
  }

  async function loadDocuments(kbId: string) {
    setIsLoadingDocs(true);
    setError("");
    try {
      const response = await fetch(`/api/rag/knowledge_bases/${kbId}/documents`);
      if (!response.ok) throw new Error(await readError(response));
      const data = (await response.json()) as DocumentListResponse;
      setDocuments(data.documents);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "文档列表加载失败。");
    } finally {
      setIsLoadingDocs(false);
    }
  }

  async function loadPipeline(kbId: string) {
    setIsLoadingPipeline(true);
    setPipelineError("");
    try {
      const query = new URLSearchParams({ kb_id: kbId }).toString();
      const [assetsResponse, artifactsResponse, draftResponse] = await Promise.all([
        fetch(`/api/rag/pipeline/assets?${query}`),
        fetch(`/api/rag/pipeline/artifacts?${query}`),
        fetch(`/api/rag/pipeline/draft?${query}`),
      ]);
      if (!assetsResponse.ok) throw new Error(await readError(assetsResponse));
      if (!artifactsResponse.ok) throw new Error(await readError(artifactsResponse));
      if (!draftResponse.ok) throw new Error(await readError(draftResponse));
      const assetsData = (await assetsResponse.json()) as PipelineAssetListResponse;
      const artifactsData = (await artifactsResponse.json()) as PipelineArtifactListResponse;
      const draftData = (await draftResponse.json()) as PipelineDraftResponse;
      setPipelineAssets(assetsData.assets);
      setPipelineArtifacts(artifactsData.artifacts);
      setPipelineDraft(draftData);
    } catch (loadError) {
      setPipelineError(
        loadError instanceof Error ? loadError.message : "知识流水线加载失败。",
      );
    } finally {
      setIsLoadingPipeline(false);
    }
  }

  async function createKnowledgeBase() {
    const name = newKbName.trim();
    if (!name || isCreating) return;

    setIsCreating(true);
    setError("");
    setNotice("");
    try {
      const response = await fetch("/api/rag/knowledge_bases", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name }),
      });
      if (!response.ok) throw new Error(await readError(response));
      const created = (await response.json()) as KnowledgeBase;
      setShowCreateModal(false);
      setNewKbName("");
      setNotice(`知识库「${created.name}」已创建。`);
      await loadKnowledgeBases(created.id);
    } catch (createError) {
      setError(createError instanceof Error ? createError.message : "创建知识库失败。");
    } finally {
      setIsCreating(false);
    }
  }

  async function deleteKnowledgeBase(kb: KnowledgeBase) {
    if (!window.confirm(`确认删除知识库「${kb.name}」及其中所有文档吗？`)) return;

    setError("");
    setNotice("");
    try {
      const response = await fetch(`/api/rag/knowledge_bases/${kb.id}`, {
        method: "DELETE",
      });
      if (!response.ok) throw new Error(await readError(response));
      setNotice(`知识库「${kb.name}」已删除。`);
      await loadKnowledgeBases();
    } catch (deleteError) {
      setError(deleteError instanceof Error ? deleteError.message : "删除知识库失败。");
    }
  }

  async function uploadFile(file: File) {
    if (!selectedKbId || isUploading) return;
    const validationError = validateFile(file);
    if (validationError) {
      setError(validationError);
      return;
    }

    setIsUploading(true);
    setError("");
    setNotice("");
    try {
      const form = new FormData();
      form.append("file", file);
      const response = await fetch(
        `/api/rag/knowledge_bases/${selectedKbId}/documents`,
        {
          method: "POST",
          body: form,
        },
      );
      if (!response.ok) throw new Error(await readError(response));
      const uploaded = (await response.json()) as RagDocument;
      setNotice(`文档「${uploaded.filename}」已入库，切成 ${uploaded.chunk_count} 个片段。`);
      await Promise.all([loadDocuments(selectedKbId), loadKnowledgeBases(selectedKbId)]);
      if (isPipelineOpen) await loadPipeline(selectedKbId);
    } catch (uploadError) {
      setError(uploadError instanceof Error ? uploadError.message : "上传文档失败。");
    } finally {
      setIsUploading(false);
    }
  }

  async function deleteDocument(document: RagDocument) {
    if (!window.confirm(`确认删除文档「${document.filename}」吗？`)) return;

    setError("");
    setNotice("");
    try {
      const response = await fetch(`/api/rag/documents/${document.id}`, {
        method: "DELETE",
      });
      if (!response.ok) throw new Error(await readError(response));
      setNotice(`文档「${document.filename}」已删除。`);
      await Promise.all([loadDocuments(selectedKbId), loadKnowledgeBases(selectedKbId)]);
      if (isPipelineOpen) await loadPipeline(selectedKbId);
    } catch (deleteError) {
      setError(deleteError instanceof Error ? deleteError.message : "删除文档失败。");
    }
  }

  function handleDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setIsDragging(false);
    const file = event.dataTransfer.files[0];
    if (file) void uploadFile(file);
  }

  return (
    <PageContainer
      activeResource="prompts"
      maxWidthClassName="max-w-[1760px]"
      sidebar={
        <div>
          <p className="text-sm font-semibold text-white">资料库服务台</p>
          <p className="mt-2 text-sm leading-6 text-slate-400">
            本地 RAG 已接管资料库：上传文档后自动解析、切块、向量化，面试间可以直接引用。
          </p>
          <div className="mt-4 rounded-lg border border-hire-300/20 bg-hire-300/10 p-3 text-xs leading-5 text-hire-50">
            支持 TXT、Markdown、PDF，单文件上限 10MB。
          </div>
        </div>
      }
    >
      <header className="mb-6 overflow-hidden rounded-lg border border-hire-300/20 bg-[linear-gradient(135deg,rgba(67,20,7,0.82),rgba(6,9,22,0.95)_52%,rgba(8,51,68,0.5))] p-6 shadow-prism">
        <p className="text-sm font-semibold text-hire-100">RAG 资料库</p>
        <div className="mt-3 flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <h1 className="text-3xl font-semibold text-white sm:text-4xl">
              知识库管理
            </h1>
            <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-300">
              像整理候选人档案一样管理你的资料：创建资料库、上传文档、让模型回答时带着引用说话。
            </p>
          </div>
          <button
            className="rounded-full bg-hire-300 px-5 py-2 text-sm font-semibold text-ink-950 shadow-[0_0_24px_rgba(251,191,36,0.25)] transition hover:bg-hire-200 active:scale-[0.98]"
            onClick={() => setShowCreateModal(true)}
            type="button"
          >
            新建知识库
          </button>
        </div>
      </header>

      {(error || notice) ? (
        <div
          className={`mb-5 rounded-lg border px-4 py-3 text-sm ${
            error
              ? "border-rose-300/25 bg-rose-400/10 text-rose-100"
              : "border-emerald-300/25 bg-emerald-400/10 text-emerald-100"
          }`}
        >
          {error || notice}
        </div>
      ) : null}

      <div className="grid gap-6 xl:grid-cols-[360px_minmax(0,1fr)]">
        <section className="surface-panel rounded-lg p-4">
          <div className="flex items-center justify-between gap-3">
            <div>
              <h2 className="text-lg font-semibold text-white">资料库列表</h2>
              <p className="mt-1 text-xs text-slate-400">
                {knowledgeBases.length} 个资料库正在待命
              </p>
            </div>
            <button
              className="rounded-full border border-white/10 bg-white/[0.06] px-3 py-1.5 text-xs font-semibold text-slate-200 transition hover:border-hire-300/35 hover:bg-hire-300/10 hover:text-hire-100"
              onClick={() => void loadKnowledgeBases()}
              type="button"
            >
              刷新
            </button>
          </div>

          <div className="mt-4 space-y-3">
            {isLoadingKbs ? (
              <div className="rounded-lg border border-white/10 bg-white/[0.04] p-4 text-sm text-slate-400">
                正在整理资料库名册...
              </div>
            ) : knowledgeBases.length === 0 ? (
              <div className="rounded-lg border border-dashed border-white/15 bg-white/[0.035] p-5 text-sm leading-6 text-slate-400">
                资料库展台还空着。先新建一个知识库，再上传你的文档。
              </div>
            ) : (
              knowledgeBases.map((kb) => (
                <article
                  className={`rounded-lg border p-4 transition ${
                    kb.id === selectedKbId
                      ? "border-hire-300/50 bg-hire-300/10 shadow-[0_0_28px_rgba(251,191,36,0.16)]"
                      : "border-white/10 bg-white/[0.045] hover:border-hire-300/25 hover:bg-white/[0.07]"
                  }`}
                  key={kb.id}
                >
                  <button
                    className="block w-full text-left"
                    onClick={() => setSelectedKbId(kb.id)}
                    type="button"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <h3 className="font-semibold text-white">{kb.name}</h3>
                        <p className="mt-1 text-xs text-slate-400">
                          {kb.document_count} 份文档 · 更新于 {formatDate(kb.updated_at)}
                        </p>
                      </div>
                      <span className="rounded-full border border-white/10 bg-white/[0.06] px-2 py-1 text-[11px] font-semibold text-slate-300">
                        打开
                      </span>
                    </div>
                  </button>
                  <button
                    className="mt-3 text-xs font-semibold text-rose-200 transition hover:text-rose-100"
                    onClick={() => void deleteKnowledgeBase(kb)}
                    type="button"
                  >
                    删除资料库
                  </button>
                </article>
              ))
            )}
          </div>
        </section>

        <section className="surface-panel min-h-[560px] rounded-lg p-4 sm:p-5">
          {selectedKnowledgeBase ? (
            <>
              <div className="flex flex-col gap-4 border-b border-white/10 pb-5 lg:flex-row lg:items-start lg:justify-between">
                <div>
                  <p className="text-sm font-semibold text-hire-100">当前资料库</p>
                  <h2 className="mt-2 text-2xl font-semibold text-white">
                    {selectedKnowledgeBase.name}
                  </h2>
                  <p className="mt-2 text-sm text-slate-400">
                    {selectedKnowledgeBase.document_count} 份文档，创建于{" "}
                    {formatDate(selectedKnowledgeBase.created_at)}
                  </p>
                </div>
                <button
                  className="rounded-full border border-hire-300/30 bg-hire-300/10 px-4 py-2 text-sm font-semibold text-hire-100 transition hover:bg-hire-300/20"
                  onClick={() => fileInputRef.current?.click()}
                  type="button"
                >
                  上传文档
                </button>
              </div>

              <input
                accept=".txt,.md,.markdown,.pdf,text/plain,text/markdown,application/pdf"
                className="hidden"
                onChange={(event) => {
                  const file = event.target.files?.[0];
                  if (file) void uploadFile(file);
                  event.target.value = "";
                }}
                ref={fileInputRef}
                type="file"
              />

              <div
                className={`mt-5 rounded-lg border border-dashed p-6 text-center transition ${
                  isDragging
                    ? "border-hire-300/70 bg-hire-300/10"
                    : "border-white/15 bg-white/[0.035] hover:border-hire-300/35"
                }`}
                onDragLeave={() => setIsDragging(false)}
                onDragOver={(event) => {
                  event.preventDefault();
                  setIsDragging(true);
                }}
                onDrop={handleDrop}
              >
                <p className="text-sm font-semibold text-white">
                  {isUploading ? "正在入库并生成索引..." : "拖拽文档到这里，或点击上传"}
                </p>
                <p className="mt-2 text-xs text-slate-400">
                  支持 .txt / .md / .pdf，上传后会自动切块、向量化并写入检索索引。
                </p>
                <button
                  className="mt-4 rounded-full bg-white/[0.08] px-4 py-2 text-sm font-semibold text-slate-100 transition hover:bg-white/[0.12] disabled:cursor-not-allowed disabled:opacity-50"
                  disabled={isUploading}
                  onClick={() => fileInputRef.current?.click()}
                  type="button"
                >
                  {isUploading ? "处理中" : "选择文件"}
                </button>
              </div>

              <section className="mt-5 overflow-hidden rounded-lg border border-white/10 bg-white/[0.035]">
                <button
                  className="flex w-full flex-col gap-3 px-4 py-3 text-left transition hover:bg-white/[0.04] sm:flex-row sm:items-center sm:justify-between"
                  onClick={() => setIsPipelineOpen((value) => !value)}
                  type="button"
                >
                  <span>
                    <span className="block text-sm font-semibold text-white">
                      知识流水线 Beta
                    </span>
                    <span className="mt-1 block text-xs leading-5 text-slate-400">
                      FileAsset → Artifact → Chunk → CitationAnchor 只读元数据视图
                    </span>
                  </span>
                  <span className="rounded-full border border-hire-300/25 bg-hire-300/10 px-3 py-1 text-xs font-semibold text-hire-100">
                    {isPipelineOpen ? "收起" : "展开"}
                  </span>
                </button>

                {isPipelineOpen ? (
                  <div className="border-t border-white/10 px-4 py-4">
                    {isLoadingPipeline ? (
                      <p className="text-sm text-slate-400">正在读取知识流水线元数据...</p>
                    ) : pipelineError ? (
                      <p className="text-sm text-rose-100">{pipelineError}</p>
                    ) : (
                      <>
                        <div className="rounded-lg border border-hire-300/20 bg-hire-300/10 p-3 text-xs leading-5 text-hire-50">
                          当前为只读流水线草稿：展示数据源、处理器、分块器与图像理解 stage，
                          不改变上传、切分、向量化或检索行为。
                        </div>

                        <div className="mt-3 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                          {(pipelineDraft?.stages ?? []).map((stage, index) => (
                            <div
                              className="rounded-lg border border-white/10 bg-ink-950/35 p-3"
                              key={stage.id}
                            >
                              <div className="flex items-start justify-between gap-3">
                                <div>
                                  <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
                                    Stage {index + 1}
                                  </p>
                                  <p className="mt-1 text-sm font-semibold text-white">
                                    {stage.title}
                                  </p>
                                </div>
                                <span
                                  className={`rounded-full border px-2 py-0.5 text-[11px] font-semibold ${stageStatusClass(
                                    stage.status,
                                  )}`}
                                >
                                  {stageStatusLabel(stage.status)}
                                </span>
                              </div>
                              <p className="mt-3 text-2xl font-semibold text-white">
                                {stage.item_count}
                              </p>
                              <p className="mt-2 min-h-10 text-xs leading-5 text-slate-400">
                                {stage.summary}
                              </p>
                            </div>
                          ))}
                        </div>

                        <div className="mt-3 grid gap-3 sm:grid-cols-3">
                          <div className="rounded-lg border border-white/10 bg-white/[0.025] p-3">
                            <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
                              FileAssets
                            </p>
                            <p className="mt-2 text-lg font-semibold text-white">
                              {pipelineAssets.length}
                            </p>
                          </div>
                          <div className="rounded-lg border border-white/10 bg-white/[0.025] p-3">
                            <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
                              Artifacts
                            </p>
                            <p className="mt-2 text-lg font-semibold text-white">
                              {pipelineArtifacts.length}
                            </p>
                          </div>
                          <div className="rounded-lg border border-white/10 bg-white/[0.025] p-3">
                            <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
                              Chunks
                            </p>
                            <p className="mt-2 text-lg font-semibold text-white">
                              {pipelineChunkCount}
                            </p>
                          </div>
                        </div>

                        <div className="mt-4">
                          <div className="flex items-center justify-between gap-3">
                            <p className="text-xs font-semibold text-slate-300">
                              最近 Artifacts
                            </p>
                            <button
                              className="text-xs font-semibold text-hire-100 transition hover:text-hire-50"
                              onClick={(event) => {
                                event.stopPropagation();
                                void loadPipeline(selectedKbId);
                              }}
                              type="button"
                            >
                              刷新
                            </button>
                          </div>
                          {pipelineArtifacts.length === 0 ? (
                            <p className="mt-3 rounded-lg border border-dashed border-white/10 p-3 text-sm text-slate-400">
                              当前资料库还没有可观察的文档产物。
                            </p>
                          ) : (
                            <div className="mt-3 divide-y divide-white/10 overflow-hidden rounded-lg border border-white/10">
                              {pipelineArtifacts.slice(0, 5).map((artifact) => (
                                <div
                                  className="grid gap-2 bg-ink-950/30 p-3 text-sm sm:grid-cols-[minmax(0,1fr)_auto]"
                                  key={artifact.artifact_id}
                                >
                                  <div className="min-w-0">
                                    <p className="truncate font-semibold text-white">
                                      {artifact.title}
                                    </p>
                                    <p className="mt-1 text-xs text-slate-400">
                                      {artifact.artifact_id}
                                    </p>
                                  </div>
                                  <p className="text-xs font-semibold text-hire-100">
                                    {artifact.chunk_count} chunks
                                  </p>
                                </div>
                              ))}
                            </div>
                          )}
                        </div>
                      </>
                    )}
                  </div>
                ) : null}
              </section>

              <div className="mt-6">
                <div className="flex items-center justify-between">
                  <h3 className="text-lg font-semibold text-white">文档清单</h3>
                  <button
                    className="text-xs font-semibold text-slate-300 transition hover:text-white"
                    onClick={() => void loadDocuments(selectedKbId)}
                    type="button"
                  >
                    刷新文档
                  </button>
                </div>

                <div className="mt-3 overflow-hidden rounded-lg border border-white/10">
                  {isLoadingDocs ? (
                    <div className="bg-white/[0.035] p-5 text-sm text-slate-400">
                      正在翻资料夹...
                    </div>
                  ) : documents.length === 0 ? (
                    <div className="bg-white/[0.035] p-6 text-sm leading-6 text-slate-400">
                      还没有文档。上传第一份资料后，面试间就能引用它回答问题。
                    </div>
                  ) : (
                    <div className="divide-y divide-white/10">
                      {documents.map((document) => (
                        <article
                          className="grid gap-3 bg-white/[0.035] p-4 transition hover:bg-white/[0.055] md:grid-cols-[minmax(0,1fr)_auto]"
                          key={document.id}
                        >
                          <div>
                            <h4 className="font-semibold text-white">
                              {document.filename}
                            </h4>
                            <p className="mt-1 text-xs text-slate-400">
                              {document.chunk_count} 个片段 · {formatFileSize(document.size)} ·{" "}
                              {formatDate(document.created_at)}
                            </p>
                          </div>
                          <button
                            className="w-fit rounded-full border border-rose-300/20 bg-rose-300/10 px-3 py-1.5 text-xs font-semibold text-rose-100 transition hover:bg-rose-300/20"
                            onClick={() => void deleteDocument(document)}
                            type="button"
                          >
                            删除
                          </button>
                        </article>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            </>
          ) : (
            <div className="flex min-h-[480px] flex-col items-center justify-center text-center">
              <div className="rounded-lg border border-hire-300/20 bg-hire-300/10 px-4 py-3 text-3xl">
                📚
              </div>
              <h2 className="mt-5 text-2xl font-semibold text-white">
                先搭一个资料库展台
              </h2>
              <p className="mt-3 max-w-md text-sm leading-6 text-slate-400">
                创建知识库后，你可以上传文档并在面试间选择它，让模型基于资料回答。
              </p>
              <button
                className="mt-6 rounded-full bg-hire-300 px-5 py-2 text-sm font-semibold text-ink-950 transition hover:bg-hire-200"
                onClick={() => setShowCreateModal(true)}
                type="button"
              >
                新建知识库
              </button>
            </div>
          )}
        </section>
      </div>

      {showCreateModal ? (
        <div className="fixed inset-0 z-[80] flex items-center justify-center bg-ink-950/80 p-4 backdrop-blur">
          <div className="w-full max-w-md rounded-lg border border-white/10 bg-surface-900 p-5 shadow-prism">
            <h2 className="text-xl font-semibold text-white">新建知识库</h2>
            <p className="mt-2 text-sm leading-6 text-slate-400">
              给这个资料库起个好记的名字，比如“产品手册”或“客户问答”。
            </p>
            <input
              autoFocus
              className="mt-5 w-full rounded-lg border border-white/10 bg-white/[0.06] px-4 py-3 text-sm text-white outline-none transition placeholder:text-slate-500 focus:border-hire-300/50 focus:ring-4 focus:ring-hire-300/10"
              onChange={(event) => setNewKbName(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") void createKnowledgeBase();
              }}
              placeholder="输入知识库名称"
              value={newKbName}
            />
            <div className="mt-5 flex justify-end gap-3">
              <button
                className="rounded-full border border-white/10 px-4 py-2 text-sm font-semibold text-slate-200 transition hover:bg-white/[0.06]"
                onClick={() => {
                  setShowCreateModal(false);
                  setNewKbName("");
                }}
                type="button"
              >
                取消
              </button>
              <button
                className="rounded-full bg-hire-300 px-4 py-2 text-sm font-semibold text-ink-950 transition hover:bg-hire-200 disabled:cursor-not-allowed disabled:opacity-50"
                disabled={!newKbName.trim() || isCreating}
                onClick={() => void createKnowledgeBase()}
                type="button"
              >
                {isCreating ? "创建中" : "创建"}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </PageContainer>
  );
}
