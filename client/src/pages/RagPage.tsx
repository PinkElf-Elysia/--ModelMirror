import { type DragEvent, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
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
  config?: Record<string, unknown>;
  metadata?: Record<string, unknown>;
}

interface PipelineDraftResponse {
  kb_id: string;
  draft_id: string;
  version: number;
  updated_at: number;
  editable: boolean;
  stages: PipelineDraftStage[];
  stage_count: number;
}

interface PipelinePreflightStage {
  id: string;
  kind: string;
  title: string;
  status: string;
  severity: string;
  summary: string;
  metadata?: Record<string, unknown>;
}

interface PipelinePreflightResponse {
  kb_id: string;
  draft_id: string;
  ready: boolean;
  warnings: string[];
  stage_checks: PipelinePreflightStage[];
  document_count: number;
  artifact_count: number;
  chunk_count: number;
}

interface PipelineDraftEdits {
  chunkSize: string;
  chunkOverlap: string;
}

interface PipelineJobStage {
  id: string;
  title: string;
  status: string;
  progress: number;
  item_count: number | null;
  error: string | null;
}

interface PipelineJob {
  job_id: string;
  kb_id: string;
  draft_version: number;
  status: string;
  stages: PipelineJobStage[];
  source_count: number;
  candidate_version_id: string;
  candidate_version: number;
  attempt: number;
  error: string | null;
  created_at: number;
  updated_at: number;
}

interface PipelineJobListResponse {
  jobs: PipelineJob[];
  job_count: number;
}

interface PipelineVersion {
  version_id: string;
  kb_id: string;
  version: number;
  status: string;
  active: boolean;
  draft_version: number;
  document_count: number;
  chunk_count: number;
  job_id: string;
  created_at: number;
  activated_at: number | null;
}

interface PipelineVersionListResponse {
  versions: PipelineVersion[];
  version_count: number;
  active_version_id: string | null;
}

interface PipelineVersionQueryResponse {
  version_id: string;
  version: number;
  answer: string;
  sources: Array<{
    chunk_id: string;
    document_name: string;
    text: string;
    score: number;
  }>;
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

function preflightSeverityClass(severity: string) {
  if (severity === "warning") return "border-amber-300/25 bg-amber-300/10 text-amber-100";
  if (severity === "error") return "border-rose-300/25 bg-rose-300/10 text-rose-100";
  return "border-emerald-300/25 bg-emerald-300/10 text-emerald-100";
}

function pipelineJobStatusLabel(status: string) {
  if (status === "queued") return "等待执行";
  if (status === "running") return "执行中";
  if (status === "succeeded") return "候选就绪";
  if (status === "failed") return "执行失败";
  if (status === "cancelled") return "已取消";
  return status;
}

function pipelineJobStatusClass(status: string) {
  if (status === "succeeded") return "border-emerald-300/25 bg-emerald-300/10 text-emerald-100";
  if (status === "running" || status === "queued") return "border-sky-300/25 bg-sky-300/10 text-sky-100";
  if (status === "failed") return "border-rose-300/25 bg-rose-300/10 text-rose-100";
  return "border-white/10 bg-white/[0.06] text-slate-300";
}

function formatConfigValue(value: unknown) {
  if (Array.isArray(value)) return value.join(", ");
  if (typeof value === "boolean") return value ? "true" : "false";
  if (value == null) return "未设置";
  return String(value);
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
  const [searchParams] = useSearchParams();
  const requestedKbId = searchParams.get("kb_id") ?? "";
  const requestedJobId = searchParams.get("job_id") ?? "";
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
  const [isPipelineOpen, setIsPipelineOpen] = useState(Boolean(requestedKbId || requestedJobId));
  const [isLoadingPipeline, setIsLoadingPipeline] = useState(false);
  const [pipelineError, setPipelineError] = useState("");
  const [pipelineAssets, setPipelineAssets] = useState<PipelineAsset[]>([]);
  const [pipelineArtifacts, setPipelineArtifacts] = useState<PipelineArtifact[]>([]);
  const [pipelineDraft, setPipelineDraft] = useState<PipelineDraftResponse | null>(null);
  const [pipelineDraftEdits, setPipelineDraftEdits] = useState<PipelineDraftEdits>({
    chunkSize: "",
    chunkOverlap: "",
  });
  const [pipelinePreflight, setPipelinePreflight] = useState<PipelinePreflightResponse | null>(null);
  const [isSavingPipelineDraft, setIsSavingPipelineDraft] = useState(false);
  const [isPreflightingPipeline, setIsPreflightingPipeline] = useState(false);
  const [pipelineDraftNotice, setPipelineDraftNotice] = useState("");
  const [pipelineJobs, setPipelineJobs] = useState<PipelineJob[]>([]);
  const [pipelineVersions, setPipelineVersions] = useState<PipelineVersion[]>([]);
  const [activePipelineVersionId, setActivePipelineVersionId] = useState<string | null>(null);
  const [selectedPipelineJobId, setSelectedPipelineJobId] = useState(requestedJobId);
  const [isExecutingPipeline, setIsExecutingPipeline] = useState(false);
  const [pipelinePreviewQuestion, setPipelinePreviewQuestion] = useState("");
  const [pipelinePreview, setPipelinePreview] = useState<PipelineVersionQueryResponse | null>(null);
  const [previewingVersionId, setPreviewingVersionId] = useState("");
  const [activatingVersionId, setActivatingVersionId] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);

  const selectedKnowledgeBase = useMemo(
    () => knowledgeBases.find((item) => item.id === selectedKbId) ?? null,
    [knowledgeBases, selectedKbId],
  );

  const pipelineChunkCount = useMemo(
    () => pipelineArtifacts.reduce((total, artifact) => total + artifact.chunk_count, 0),
    [pipelineArtifacts],
  );

  const selectedPipelineJob = useMemo(
    () => pipelineJobs.find((job) => job.job_id === selectedPipelineJobId) ?? pipelineJobs[0] ?? null,
    [pipelineJobs, selectedPipelineJobId],
  );

  const hasActivePipelineJob = useMemo(
    () => pipelineJobs.some((job) => job.status === "queued" || job.status === "running"),
    [pipelineJobs],
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
      setPipelinePreflight(null);
      setPipelineJobs([]);
      setPipelineVersions([]);
      setActivePipelineVersionId(null);
      setSelectedPipelineJobId("");
      setPipelinePreview(null);
      setPipelineDraftNotice("");
      setPipelineError("");
      return;
    }
    void loadDocuments(selectedKbId);
    if (isPipelineOpen) void loadPipeline(selectedKbId);
  }, [isPipelineOpen, selectedKbId]);

  useEffect(() => {
    if (!isPipelineOpen || !selectedKbId || !hasActivePipelineJob) return;
    const timer = window.setInterval(() => {
      void loadPipelineRuntime(selectedKbId);
    }, 2000);
    return () => window.clearInterval(timer);
  }, [hasActivePipelineJob, isPipelineOpen, selectedKbId]);

  async function loadKnowledgeBases(nextSelectedId?: string) {
    setIsLoadingKbs(true);
    setError("");
    try {
      const response = await fetch("/api/rag/knowledge_bases");
      if (!response.ok) throw new Error(await readError(response));
      const data = (await response.json()) as KnowledgeBaseListResponse;
      setKnowledgeBases(data.knowledge_bases);
      const preferredId =
        nextSelectedId || requestedKbId || selectedKbId || data.knowledge_bases[0]?.id || "";
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
      const [assetsResponse, artifactsResponse, draftResponse, jobsResponse, versionsResponse] = await Promise.all([
        fetch(`/api/rag/pipeline/assets?${query}`),
        fetch(`/api/rag/pipeline/artifacts?${query}`),
        fetch(`/api/rag/pipeline/draft?${query}`),
        fetch(`/api/rag/pipeline/jobs?${query}&limit=20`),
        fetch(`/api/rag/pipeline/versions?${query}`),
      ]);
      if (!assetsResponse.ok) throw new Error(await readError(assetsResponse));
      if (!artifactsResponse.ok) throw new Error(await readError(artifactsResponse));
      if (!draftResponse.ok) throw new Error(await readError(draftResponse));
      if (!jobsResponse.ok) throw new Error(await readError(jobsResponse));
      if (!versionsResponse.ok) throw new Error(await readError(versionsResponse));
      const assetsData = (await assetsResponse.json()) as PipelineAssetListResponse;
      const artifactsData = (await artifactsResponse.json()) as PipelineArtifactListResponse;
      const draftData = (await draftResponse.json()) as PipelineDraftResponse;
      const jobsData = (await jobsResponse.json()) as PipelineJobListResponse;
      const versionsData = (await versionsResponse.json()) as PipelineVersionListResponse;
      setPipelineAssets(assetsData.assets);
      setPipelineArtifacts(artifactsData.artifacts);
      setPipelineDraft(draftData);
      setPipelineJobs(jobsData.jobs);
      setPipelineVersions(versionsData.versions);
      setActivePipelineVersionId(versionsData.active_version_id);
      setSelectedPipelineJobId((current) => {
        if (current && jobsData.jobs.some((job) => job.job_id === current)) return current;
        if (requestedJobId && jobsData.jobs.some((job) => job.job_id === requestedJobId)) return requestedJobId;
        return jobsData.jobs[0]?.job_id ?? "";
      });
      const chunkerStage = draftData.stages.find((stage) => stage.kind === "chunker");
      setPipelineDraftEdits({
        chunkSize: String(chunkerStage?.config?.chunk_size ?? 500),
        chunkOverlap: String(chunkerStage?.config?.chunk_overlap ?? 50),
      });
      setPipelinePreflight(null);
      setPipelineDraftNotice("");
    } catch (loadError) {
      setPipelineError(
        loadError instanceof Error ? loadError.message : "知识流水线加载失败。",
      );
    } finally {
      setIsLoadingPipeline(false);
    }
  }

  async function loadPipelineRuntime(kbId: string) {
    try {
      const query = new URLSearchParams({ kb_id: kbId }).toString();
      const [jobsResponse, versionsResponse] = await Promise.all([
        fetch(`/api/rag/pipeline/jobs?${query}&limit=20`),
        fetch(`/api/rag/pipeline/versions?${query}`),
      ]);
      if (!jobsResponse.ok) throw new Error(await readError(jobsResponse));
      if (!versionsResponse.ok) throw new Error(await readError(versionsResponse));
      const jobsData = (await jobsResponse.json()) as PipelineJobListResponse;
      const versionsData = (await versionsResponse.json()) as PipelineVersionListResponse;
      setPipelineJobs(jobsData.jobs);
      setPipelineVersions(versionsData.versions);
      setActivePipelineVersionId(versionsData.active_version_id);
      setSelectedPipelineJobId((current) =>
        current && jobsData.jobs.some((job) => job.job_id === current)
          ? current
          : jobsData.jobs[0]?.job_id ?? "",
      );
    } catch (loadError) {
      setPipelineError(
        loadError instanceof Error ? loadError.message : "知识流水线运行状态加载失败。",
      );
    }
  }

  async function savePipelineDraft() {
    if (!selectedKbId || isSavingPipelineDraft) return;
    setIsSavingPipelineDraft(true);
    setPipelineError("");
    setPipelineDraftNotice("");
    try {
      const chunkSize = Number(pipelineDraftEdits.chunkSize);
      const chunkOverlap = Number(pipelineDraftEdits.chunkOverlap);
      const response = await fetch(`/api/rag/pipeline/draft/${selectedKbId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          stages: {
            stage_chunker: {
              config: {
                chunk_size: chunkSize,
                chunk_overlap: chunkOverlap,
              },
            },
          },
        }),
      });
      if (!response.ok) throw new Error(await readError(response));
      const draftData = (await response.json()) as PipelineDraftResponse;
      const chunkerStage = draftData.stages.find((stage) => stage.kind === "chunker");
      setPipelineDraft(draftData);
      setPipelineDraftEdits({
        chunkSize: String(chunkerStage?.config?.chunk_size ?? chunkSize),
        chunkOverlap: String(chunkerStage?.config?.chunk_overlap ?? chunkOverlap),
      });
      setPipelinePreflight(null);
      setPipelineDraftNotice("流水线草稿已保存；当前不会影响已上传文档、检索结果或聊天 RAG。");
    } catch (saveError) {
      setPipelineError(saveError instanceof Error ? saveError.message : "保存流水线草稿失败。");
    } finally {
      setIsSavingPipelineDraft(false);
    }
  }

  async function runPipelinePreflight() {
    if (!selectedKbId || isPreflightingPipeline) return;
    setIsPreflightingPipeline(true);
    setPipelineError("");
    try {
      const response = await fetch(`/api/rag/pipeline/draft/${selectedKbId}/preflight`, {
        method: "POST",
      });
      if (!response.ok) throw new Error(await readError(response));
      const preflightData = (await response.json()) as PipelinePreflightResponse;
      setPipelinePreflight(preflightData);
      setPipelineDraftNotice(
        preflightData.ready
          ? "预检通过：当前草稿配置与已入库文档元数据一致。"
          : "预检完成：请查看 warnings 与 stage 检查结果。",
      );
    } catch (preflightError) {
      setPipelineError(
        preflightError instanceof Error ? preflightError.message : "运行流水线预检失败。",
      );
    } finally {
      setIsPreflightingPipeline(false);
    }
  }

  async function executePipelineDraft() {
    if (!selectedKbId || !pipelineDraft || isExecutingPipeline) return;
    setIsExecutingPipeline(true);
    setPipelineError("");
    setPipelineDraftNotice("");
    try {
      const response = await fetch(`/api/rag/pipeline/draft/${selectedKbId}/execute`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          draft_version: pipelineDraft.version,
          source_document_ids: null,
          xpert_file_refs: [],
        }),
      });
      if (!response.ok) throw new Error(await readError(response));
      const created = (await response.json()) as PipelineJob;
      setSelectedPipelineJobId(created.job_id);
      setPipelineJobs((current) => [created, ...current]);
      setPipelineDraftNotice("执行任务已创建。候选索引完成后需人工预览并激活，当前检索不会自动切换。");
      await loadPipelineRuntime(selectedKbId);
    } catch (executeError) {
      setPipelineError(
        executeError instanceof Error ? executeError.message : "知识流水线执行失败。",
      );
    } finally {
      setIsExecutingPipeline(false);
    }
  }

  async function cancelPipelineJob(jobId: string) {
    setPipelineError("");
    try {
      const response = await fetch(`/api/rag/pipeline/jobs/${jobId}/cancel`, { method: "POST" });
      if (!response.ok) throw new Error(await readError(response));
      await loadPipelineRuntime(selectedKbId);
    } catch (cancelError) {
      setPipelineError(cancelError instanceof Error ? cancelError.message : "取消任务失败。");
    }
  }

  async function retryPipelineJob(jobId: string) {
    setPipelineError("");
    try {
      const response = await fetch(`/api/rag/pipeline/jobs/${jobId}/retry`, { method: "POST" });
      if (!response.ok) throw new Error(await readError(response));
      setSelectedPipelineJobId(jobId);
      await loadPipelineRuntime(selectedKbId);
    } catch (retryError) {
      setPipelineError(retryError instanceof Error ? retryError.message : "重试任务失败。");
    }
  }

  async function previewPipelineVersion(versionId: string) {
    const question = pipelinePreviewQuestion.trim();
    if (!question || previewingVersionId) return;
    setPreviewingVersionId(versionId);
    setPipelineError("");
    try {
      const response = await fetch(`/api/rag/pipeline/versions/${versionId}/query`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question, top_k: 4 }),
      });
      if (!response.ok) throw new Error(await readError(response));
      setPipelinePreview((await response.json()) as PipelineVersionQueryResponse);
    } catch (previewError) {
      setPipelineError(previewError instanceof Error ? previewError.message : "候选版本预览失败。");
    } finally {
      setPreviewingVersionId("");
    }
  }

  async function activatePipelineVersion(versionId: string) {
    if (activatingVersionId) return;
    setActivatingVersionId(versionId);
    setPipelineError("");
    try {
      const response = await fetch(`/api/rag/pipeline/versions/${versionId}/activate`, {
        method: "POST",
      });
      if (!response.ok) throw new Error(await readError(response));
      await loadPipelineRuntime(selectedKbId);
      const activated = (await response.json()) as PipelineVersion;
      setPipelineDraftNotice(`知识索引 v${activated.version} 已激活。RAG、聊天和知识引用节点将使用该版本。`);
    } catch (activateError) {
      setPipelineError(activateError instanceof Error ? activateError.message : "激活版本失败。");
    } finally {
      setActivatingVersionId("");
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
                      FileAsset → Artifact → Chunk → 版本化索引 → CitationAnchor
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
                          草稿执行会生成隔离的候选索引。候选完成后先预览，再由你人工激活或回滚。
                        </div>

                        <div className="mt-3 rounded-lg border border-sky-300/20 bg-sky-300/10 p-3 text-xs leading-5 text-sky-100">
                          保存草稿本身不会改变检索。只有显式激活候选版本后，RAG、聊天和知识引用节点才会切换索引。
                        </div>

                        <div className="mt-3 flex flex-col gap-3 rounded-lg border border-white/10 bg-ink-950/35 p-3 sm:flex-row sm:items-center sm:justify-between">
                          <div>
                            <p className="text-xs font-semibold text-slate-300">
                              草稿版本 v{pipelineDraft?.version ?? 1}
                            </p>
                            <p className="mt-1 text-xs text-slate-500">
                              {pipelineDraft?.updated_at
                                ? `更新于 ${formatDate(pipelineDraft.updated_at)}`
                                : "尚未保存草稿"}
                            </p>
                          </div>
                          <div className="flex flex-wrap gap-2">
                            <button
                              className="rounded-full border border-hire-300/25 bg-hire-300/10 px-3 py-1.5 text-xs font-semibold text-hire-100 transition hover:bg-hire-300/20 disabled:cursor-not-allowed disabled:opacity-50"
                              disabled={isSavingPipelineDraft || !pipelineDraft}
                              onClick={() => void savePipelineDraft()}
                              type="button"
                            >
                              {isSavingPipelineDraft ? "保存中..." : "保存草稿"}
                            </button>
                            <button
                              className="rounded-full border border-white/10 bg-white/[0.06] px-3 py-1.5 text-xs font-semibold text-slate-200 transition hover:bg-white/[0.1] disabled:cursor-not-allowed disabled:opacity-50"
                              disabled={isPreflightingPipeline || !pipelineDraft}
                              onClick={() => void runPipelinePreflight()}
                              type="button"
                            >
                              {isPreflightingPipeline ? "预检中..." : "运行预检"}
                            </button>
                            <button
                              className="inline-flex items-center gap-1.5 rounded-lg bg-hire-300 px-3 py-1.5 text-xs font-semibold text-ink-950 transition hover:bg-hire-200 disabled:cursor-not-allowed disabled:opacity-50"
                              disabled={isExecutingPipeline || !pipelineDraft || documents.length === 0}
                              onClick={() => void executePipelineDraft()}
                              title={documents.length === 0 ? "请先上传至少一份文档" : "构建候选知识索引"}
                              type="button"
                            >
                              {isExecutingPipeline ? "创建任务中..." : "执行草稿"}
                            </button>
                          </div>
                        </div>

                        {pipelineDraftNotice ? (
                          <div className="mt-3 rounded-lg border border-emerald-300/20 bg-emerald-300/10 p-3 text-xs leading-5 text-emerald-100">
                            {pipelineDraftNotice}
                          </div>
                        ) : null}

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
                              {stage.config ? (
                                <dl className="mt-3 space-y-1 border-t border-white/10 pt-3 text-[11px] text-slate-400">
                                  {Object.entries(stage.config).map(([key, value]) => (
                                    <div
                                      className="flex items-start justify-between gap-2"
                                      key={key}
                                    >
                                      <dt className="shrink-0 text-slate-500">{key}</dt>
                                      <dd className="break-all text-right text-slate-300">
                                        {formatConfigValue(value)}
                                      </dd>
                                    </div>
                                  ))}
                                </dl>
                              ) : null}
                            </div>
                          ))}
                        </div>

                        <div className="mt-3 grid gap-3 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,0.9fr)]">
                          <div className="rounded-lg border border-white/10 bg-white/[0.025] p-4">
                            <div className="flex items-start justify-between gap-3">
                              <div>
                                <p className="text-sm font-semibold text-white">草稿配置</p>
                                <p className="mt-1 text-xs leading-5 text-slate-400">
                                  仅保存未来配置，不会重跑当前上传、切分或向量化流程。
                                </p>
                              </div>
                              <span className="rounded-full border border-white/10 bg-white/[0.06] px-2 py-0.5 text-[11px] font-semibold text-slate-300">
                                editable
                              </span>
                            </div>
                            <div className="mt-3 grid gap-3 sm:grid-cols-2">
                              <label className="block rounded-lg border border-white/10 bg-ink-950/35 p-3">
                                <span className="text-xs font-semibold text-slate-300">
                                  分块大小
                                </span>
                                <input
                                  className="mt-2 w-full rounded-lg border border-white/10 bg-white/[0.06] px-3 py-2 text-sm text-white outline-none transition focus:border-hire-300/50 focus:ring-4 focus:ring-hire-300/10"
                                  max={4000}
                                  min={100}
                                  onChange={(event) =>
                                    setPipelineDraftEdits((current) => ({
                                      ...current,
                                      chunkSize: event.target.value,
                                    }))
                                  }
                                  type="number"
                                  value={pipelineDraftEdits.chunkSize}
                                />
                              </label>
                              <label className="block rounded-lg border border-white/10 bg-ink-950/35 p-3">
                                <span className="text-xs font-semibold text-slate-300">
                                  重叠字符
                                </span>
                                <input
                                  className="mt-2 w-full rounded-lg border border-white/10 bg-white/[0.06] px-3 py-2 text-sm text-white outline-none transition focus:border-hire-300/50 focus:ring-4 focus:ring-hire-300/10"
                                  min={0}
                                  onChange={(event) =>
                                    setPipelineDraftEdits((current) => ({
                                      ...current,
                                      chunkOverlap: event.target.value,
                                    }))
                                  }
                                  type="number"
                                  value={pipelineDraftEdits.chunkOverlap}
                                />
                              </label>
                            </div>
                            <div className="mt-3 grid gap-2 text-xs text-slate-400 sm:grid-cols-2">
                              <div className="rounded-lg border border-white/10 bg-white/[0.03] p-3">
                                数据源锁定为 uploaded_files
                              </div>
                              <div className="rounded-lg border border-white/10 bg-white/[0.03] p-3">
                                处理器锁定为 local_document_parser
                              </div>
                              <div className="rounded-lg border border-white/10 bg-white/[0.03] p-3 sm:col-span-2">
                                图像理解仍为 planned/disabled，占位展示但不可启用。
                              </div>
                            </div>
                          </div>

                          <div className="rounded-lg border border-white/10 bg-white/[0.025] p-4">
                            <div className="flex items-center justify-between gap-3">
                              <p className="text-sm font-semibold text-white">预检结果</p>
                              {pipelinePreflight ? (
                                <span
                                  className={`rounded-full border px-2 py-0.5 text-[11px] font-semibold ${
                                    pipelinePreflight.ready
                                      ? "border-emerald-300/25 bg-emerald-300/10 text-emerald-100"
                                      : "border-amber-300/25 bg-amber-300/10 text-amber-100"
                                  }`}
                                >
                                  {pipelinePreflight.ready ? "ready" : "warnings"}
                                </span>
                              ) : null}
                            </div>
                            {!pipelinePreflight ? (
                              <p className="mt-3 text-xs leading-5 text-slate-400">
                                点击“运行预检”检查当前草稿与已入库文档、Artifact、Chunk 的一致性。
                              </p>
                            ) : (
                              <div className="mt-3 space-y-3">
                                {pipelinePreflight.warnings.length > 0 ? (
                                  <div className="rounded-lg border border-amber-300/20 bg-amber-300/10 p-3 text-xs leading-5 text-amber-100">
                                    {pipelinePreflight.warnings.map((warning) => (
                                      <p key={warning}>{warning}</p>
                                    ))}
                                  </div>
                                ) : (
                                  <div className="rounded-lg border border-emerald-300/20 bg-emerald-300/10 p-3 text-xs text-emerald-100">
                                    当前草稿通过预检。
                                  </div>
                                )}
                                <div className="space-y-2">
                                  {pipelinePreflight.stage_checks.map((check) => (
                                    <div
                                      className="rounded-lg border border-white/10 bg-ink-950/35 p-3"
                                      key={check.id}
                                    >
                                      <div className="flex items-center justify-between gap-3">
                                        <p className="text-xs font-semibold text-white">
                                          {check.title}
                                        </p>
                                        <span
                                          className={`rounded-full border px-2 py-0.5 text-[11px] font-semibold ${preflightSeverityClass(
                                            check.severity,
                                          )}`}
                                        >
                                          {check.severity}
                                        </span>
                                      </div>
                                      <p className="mt-2 text-xs leading-5 text-slate-400">
                                        {check.summary}
                                      </p>
                                    </div>
                                  ))}
                                </div>
                              </div>
                            )}
                          </div>
                        </div>

                        <div className="mt-3 grid gap-3 xl:grid-cols-[minmax(0,1.05fr)_minmax(0,0.95fr)]">
                          <section className="rounded-lg border border-white/10 bg-white/[0.025] p-4">
                            <div className="flex items-start justify-between gap-3">
                              <div>
                                <h3 className="text-sm font-semibold text-white">执行任务</h3>
                                <p className="mt-1 text-xs leading-5 text-slate-400">
                                  五阶段构建候选索引。失败或取消不会影响当前激活版本。
                                </p>
                              </div>
                              <button
                                className="rounded-md border border-white/10 px-2.5 py-1.5 text-xs font-semibold text-slate-300 transition hover:bg-white/[0.07] hover:text-white"
                                onClick={() => void loadPipelineRuntime(selectedKbId)}
                                type="button"
                              >
                                刷新
                              </button>
                            </div>

                            {pipelineJobs.length > 0 ? (
                              <div className="mt-3 flex gap-2 overflow-x-auto pb-1">
                                {pipelineJobs.slice(0, 8).map((job) => (
                                  <button
                                    className={`shrink-0 rounded-md border px-2.5 py-1.5 text-left text-[11px] transition ${
                                      selectedPipelineJob?.job_id === job.job_id
                                        ? "border-hire-300/45 bg-hire-300/10 text-hire-100"
                                        : "border-white/10 bg-white/[0.035] text-slate-400 hover:text-slate-200"
                                    }`}
                                    key={job.job_id}
                                    onClick={() => setSelectedPipelineJobId(job.job_id)}
                                    type="button"
                                  >
                                    v{job.candidate_version} · {pipelineJobStatusLabel(job.status)}
                                  </button>
                                ))}
                              </div>
                            ) : null}

                            {selectedPipelineJob ? (
                              <div className="mt-3">
                                <div className="flex flex-wrap items-center justify-between gap-2 border-b border-white/10 pb-3">
                                  <div>
                                    <p className="font-mono text-[11px] text-slate-300">{selectedPipelineJob.job_id}</p>
                                    <p className="mt-1 text-[11px] text-slate-500">
                                      {selectedPipelineJob.source_count} 个来源 · attempt {selectedPipelineJob.attempt}
                                    </p>
                                  </div>
                                  <span className={`rounded-full border px-2 py-0.5 text-[11px] font-semibold ${pipelineJobStatusClass(selectedPipelineJob.status)}`}>
                                    {pipelineJobStatusLabel(selectedPipelineJob.status)}
                                  </span>
                                </div>

                                <div className="mt-3 space-y-2">
                                  {selectedPipelineJob.stages.map((stage) => (
                                    <div className="grid grid-cols-[86px_minmax(0,1fr)_auto] items-center gap-2" key={stage.id}>
                                      <span className="text-[11px] font-medium text-slate-300">{stage.title}</span>
                                      <div className="h-1.5 overflow-hidden rounded-full bg-white/[0.07]">
                                        <div
                                          className={`h-full rounded-full transition-[width] duration-200 ${
                                            stage.status === "failed" ? "bg-rose-300" : "bg-hire-300"
                                          }`}
                                          style={{ width: `${Math.max(0, Math.min(stage.progress, 100))}%` }}
                                        />
                                      </div>
                                      <span className="w-14 text-right text-[10px] text-slate-500">{stage.status}</span>
                                    </div>
                                  ))}
                                </div>

                                {selectedPipelineJob.error ? (
                                  <p className="mt-3 rounded-md border border-rose-300/20 bg-rose-300/10 px-3 py-2 text-xs leading-5 text-rose-100">
                                    {selectedPipelineJob.error}
                                  </p>
                                ) : null}

                                <div className="mt-3 flex justify-end gap-2">
                                  {selectedPipelineJob.status === "queued" || selectedPipelineJob.status === "running" ? (
                                    <button
                                      className="inline-flex items-center gap-1.5 rounded-md border border-rose-300/20 bg-rose-300/10 px-3 py-1.5 text-xs font-semibold text-rose-100 transition hover:bg-rose-300/15"
                                      onClick={() => void cancelPipelineJob(selectedPipelineJob.job_id)}
                                      type="button"
                                    >
                                      取消任务
                                    </button>
                                  ) : null}
                                  {selectedPipelineJob.status === "failed" || selectedPipelineJob.status === "cancelled" ? (
                                    <button
                                      className="inline-flex items-center gap-1.5 rounded-md border border-white/10 bg-white/[0.06] px-3 py-1.5 text-xs font-semibold text-slate-200 transition hover:bg-white/[0.1]"
                                      onClick={() => void retryPipelineJob(selectedPipelineJob.job_id)}
                                      type="button"
                                    >
                                      重试任务
                                    </button>
                                  ) : null}
                                </div>
                              </div>
                            ) : (
                              <p className="mt-3 rounded-lg border border-dashed border-white/10 p-4 text-center text-xs leading-5 text-slate-500">
                                保存并预检草稿后，点击“执行草稿”构建第一个候选版本。
                              </p>
                            )}
                          </section>

                          <section className="rounded-lg border border-white/10 bg-white/[0.025] p-4">
                            <div className="flex items-start justify-between gap-3">
                              <div>
                                <h3 className="text-sm font-semibold text-white">索引版本</h3>
                                <p className="mt-1 text-xs leading-5 text-slate-400">
                                  候选版本先预览，再人工激活。激活旧版本即完成回滚。
                                </p>
                              </div>
                              <span className="rounded-full border border-white/10 bg-white/[0.05] px-2 py-0.5 text-[11px] text-slate-300">
                                {pipelineVersions.length} versions
                              </span>
                            </div>

                            <div className="mt-3 flex gap-2">
                              <input
                                className="min-w-0 flex-1 rounded-lg border border-white/10 bg-ink-950/45 px-3 py-2 text-xs text-white outline-none placeholder:text-slate-500 focus:border-hire-300/50"
                                onChange={(event) => setPipelinePreviewQuestion(event.target.value)}
                                placeholder="输入问题预览候选版本"
                                value={pipelinePreviewQuestion}
                              />
                            </div>

                            <div className="mt-3 divide-y divide-white/10 overflow-hidden rounded-lg border border-white/10">
                              {pipelineVersions.length > 0 ? pipelineVersions.map((versionItem) => (
                                <div className="bg-ink-950/30 p-3" key={versionItem.version_id}>
                                  <div className="flex items-start justify-between gap-3">
                                    <div>
                                      <div className="flex items-center gap-2">
                                        <p className="text-sm font-semibold text-white">v{versionItem.version}</p>
                                        {versionItem.active ? (
                                          <span className="inline-flex items-center gap-1 rounded-full border border-emerald-300/25 bg-emerald-300/10 px-2 py-0.5 text-[10px] font-semibold text-emerald-100">
                                            当前激活
                                          </span>
                                        ) : (
                                          <span className="rounded-full border border-sky-300/20 bg-sky-300/10 px-2 py-0.5 text-[10px] text-sky-100">候选</span>
                                        )}
                                      </div>
                                      <p className="mt-1 text-[10px] text-slate-500">
                                        {versionItem.document_count} 文档 · {versionItem.chunk_count} chunks · draft v{versionItem.draft_version}
                                      </p>
                                    </div>
                                    <div className="flex gap-1.5">
                                      <button
                                        className="rounded-md border border-white/10 px-2 py-1.5 text-[11px] font-semibold text-slate-300 transition hover:bg-white/[0.08] hover:text-white disabled:opacity-40"
                                        disabled={!pipelinePreviewQuestion.trim() || Boolean(previewingVersionId)}
                                        onClick={() => void previewPipelineVersion(versionItem.version_id)}
                                        type="button"
                                      >
                                        预览
                                      </button>
                                      {!versionItem.active ? (
                                        <button
                                          className="rounded-md bg-hire-300 px-2.5 py-1.5 text-[11px] font-semibold text-ink-950 transition hover:bg-hire-200 disabled:opacity-50"
                                          disabled={Boolean(activatingVersionId)}
                                          onClick={() => void activatePipelineVersion(versionItem.version_id)}
                                          type="button"
                                        >
                                          {activePipelineVersionId ? "回滚/切换" : "激活"}
                                        </button>
                                      ) : null}
                                    </div>
                                  </div>
                                </div>
                              )) : (
                                <p className="p-4 text-center text-xs leading-5 text-slate-500">
                                  尚无候选版本。执行草稿后在此预览和激活。
                                </p>
                              )}
                            </div>

                            {pipelinePreview ? (
                              <div className="mt-3 rounded-lg border border-sky-300/20 bg-sky-300/[0.07] p-3">
                                <p className="text-[11px] font-semibold text-sky-100">v{pipelinePreview.version} 预览结果</p>
                                <p className="mt-2 line-clamp-5 text-xs leading-5 text-slate-200">{pipelinePreview.answer}</p>
                                <p className="mt-2 text-[10px] text-slate-500">
                                  {pipelinePreview.sources.length} 个引用来源
                                </p>
                              </div>
                            ) : null}
                          </section>
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
