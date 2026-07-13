from __future__ import annotations

from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from .rag_service import (
    DocumentNotFoundError,
    KnowledgeBaseNotFoundError,
    PipelineDraftValidationError,
    PipelineJobNotFoundError,
    PipelineJobStateError,
    PipelineVersionNotFoundError,
    RagService,
    UnsupportedDocumentError,
)
from .pipeline_executor import KnowledgePipelineExecutor
from .processor_generator import ProcessorGenerationError


MAX_UPLOAD_BYTES = 10 * 1024 * 1024

router = APIRouter(prefix="/api/rag", tags=["rag"])
_rag_service: RagService | None = None
_pipeline_executor: KnowledgePipelineExecutor | None = None


class KnowledgeBaseCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class KnowledgeBasePayload(BaseModel):
    id: str
    name: str
    document_count: int
    created_at: float
    updated_at: float


class KnowledgeBaseListResponse(BaseModel):
    knowledge_bases: list[KnowledgeBasePayload]


class DocumentPayload(BaseModel):
    id: str
    kb_id: str
    filename: str
    size: int
    chunk_count: int
    created_at: float


class DocumentListResponse(BaseModel):
    documents: list[DocumentPayload]


class RagSourcePayload(BaseModel):
    chunk_id: str
    doc_id: str
    document_name: str
    text: str
    score: float
    matched_text: str | None = None
    vector_score: float | None = None
    fulltext_score: float | None = None
    fused_score: float | None = None
    rerank_score: float | None = None
    parent_chunk_id: str | None = None
    parent_lifted: bool = False
    chunk_type: str = "standard"
    start_char: int = 0
    end_char: int = 0


class RetrievalOptionsPayload(BaseModel):
    mode: str | None = None
    vector_weight: float | None = None
    fulltext_weight: float | None = None
    top_k: int | None = None
    score_threshold: float | None = None
    candidate_multiplier: int | None = None
    rerank_enabled: bool | None = None
    rerank_provider: str | None = None
    rerank_model: str | None = None
    rerank_top_n: int | None = None


class RagQueryRequest(BaseModel):
    kb_id: str = Field(min_length=1, max_length=160)
    question: str = Field(min_length=1, max_length=20_000)
    top_k: int | None = Field(default=None, ge=1, le=50)
    retrieval: RetrievalOptionsPayload | None = None


class RagQueryResponse(BaseModel):
    answer: str
    sources: list[RagSourcePayload]
    warnings: list[str] = Field(default_factory=list)
    retrieval: dict[str, Any] = Field(default_factory=dict)


class FileAssetPayload(BaseModel):
    file_asset_id: str
    document_id: str
    knowledge_base_id: str
    filename: str
    size: int
    extension: str
    mime_type: str | None = None
    created_at: float


class FileAssetListResponse(BaseModel):
    assets: list[FileAssetPayload]
    asset_count: int


class ArtifactPayload(BaseModel):
    artifact_id: str
    file_asset_id: str
    document_id: str
    knowledge_base_id: str
    title: str
    chunk_count: int
    created_at: float


class ArtifactListResponse(BaseModel):
    artifacts: list[ArtifactPayload]
    artifact_count: int


class KnowledgeChunkPayload(BaseModel):
    chunk_id: str
    artifact_id: str
    knowledge_base_id: str
    document_id: str
    index: int
    text_preview: str
    text_length: int


class KnowledgeChunkListResponse(BaseModel):
    artifact_id: str
    chunks: list[KnowledgeChunkPayload]
    chunk_count: int


class PipelineDraftStagePayload(BaseModel):
    id: str
    kind: str
    title: str
    status: str
    item_count: int
    summary: str
    config: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class PipelineDraftResponse(BaseModel):
    kb_id: str
    draft_id: str
    version: int
    updated_at: float
    editable: bool
    index_schema_version: int = 2
    embedding_profile: dict[str, Any] = Field(default_factory=dict)
    retrieval_profile: dict[str, Any] = Field(default_factory=dict)
    stages: list[PipelineDraftStagePayload]
    stage_count: int


class PipelineDraftStageUpdate(BaseModel):
    config: dict[str, Any] = Field(default_factory=dict)


class PipelineDraftUpdateRequest(BaseModel):
    stages: dict[str, PipelineDraftStageUpdate] = Field(default_factory=dict)
    embedding_profile: dict[str, Any] | None = None
    retrieval_profile: RetrievalOptionsPayload | None = None


class ProcessorPreviewRequest(BaseModel):
    document_id: str = Field(min_length=1, max_length=200)
    processor: dict[str, Any] | None = None


class ProcessorPreviewResponse(BaseModel):
    kb_id: str
    document_id: str
    filename: str
    title: str
    config: dict[str, Any]
    character_count: int
    block_count: int
    block_counts: dict[str, int]
    generated_count: int
    warnings: list[str]
    blocks: list[dict[str, Any]]
    generated_items: list[dict[str, Any]]


class PipelinePreflightStagePayload(BaseModel):
    id: str
    kind: str
    title: str
    status: str
    severity: str
    summary: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class PipelineDraftPreflightResponse(BaseModel):
    kb_id: str
    draft_id: str
    ready: bool
    warnings: list[str]
    stage_checks: list[PipelinePreflightStagePayload]
    document_count: int
    artifact_count: int
    chunk_count: int


class XpertFileReference(BaseModel):
    xpert_id: str = Field(min_length=1, max_length=200)
    conversation_id: str = Field(min_length=1, max_length=200)
    asset_id: str = Field(min_length=1, max_length=200)


class PipelineExecuteRequest(BaseModel):
    draft_version: int = Field(ge=1)
    source_document_ids: list[str] | None = None
    xpert_file_refs: list[XpertFileReference] = Field(default_factory=list, max_length=5)


class PipelineJobStagePayload(BaseModel):
    id: str
    title: str
    status: str
    progress: int
    item_count: int | None = None
    started_at: float | None = None
    completed_at: float | None = None
    error: str | None = None


class PipelineJobSourcePayload(BaseModel):
    source_id: str
    source_kind: str
    filename: str
    size: int
    content_mode: str
    xpert_id: str | None = None
    conversation_id: str | None = None
    asset_id: str | None = None


class PipelineDocumentResultPayload(BaseModel):
    source_id: str
    filename: str
    status: str
    attempt: int = 0
    block_count: int = 0
    generated_count: int = 0
    chunk_count: int = 0
    qa_count: int = 0
    summary_count: int = 0
    warnings: list[str] = Field(default_factory=list)
    error: str | None = None
    duration_ms: float | None = None


class PipelineJobPayload(BaseModel):
    job_id: str
    kb_id: str
    draft_id: str
    draft_version: int
    status: str
    stages: list[PipelineJobStagePayload]
    sources: list[PipelineJobSourcePayload]
    document_results: list[PipelineDocumentResultPayload] = Field(default_factory=list)
    source_count: int
    candidate_version_id: str
    candidate_version: int
    run_id: str | None = None
    attempt: int
    cancel_requested: bool
    error: str | None = None
    warnings: list[str] = Field(default_factory=list)
    created_at: float
    updated_at: float
    started_at: float | None = None
    completed_at: float | None = None


class PipelineJobListResponse(BaseModel):
    jobs: list[PipelineJobPayload]
    job_count: int


class PipelineVersionPayload(BaseModel):
    version_id: str
    kb_id: str
    version: int
    status: str
    active: bool
    draft_id: str
    draft_version: int
    source_summary: list[PipelineJobSourcePayload]
    document_count: int
    chunk_count: int
    block_count: int = 0
    qa_count: int = 0
    summary_count: int = 0
    processor_profile: dict[str, Any] = Field(default_factory=dict)
    document_results: list[PipelineDocumentResultPayload] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    job_id: str
    created_at: float
    activated_at: float | None = None
    index_schema_version: int = 1
    embedding_profile: dict[str, Any] = Field(default_factory=dict)
    retrieval_profile: dict[str, Any] = Field(default_factory=dict)
    vector_index_ready: bool = True
    lexical_index_ready: bool = False


class PipelineVersionListResponse(BaseModel):
    versions: list[PipelineVersionPayload]
    version_count: int
    active_version_id: str | None = None


class PipelineVersionQueryRequest(BaseModel):
    question: str = Field(min_length=1, max_length=20_000)
    top_k: int | None = Field(default=None, ge=1, le=50)
    retrieval: RetrievalOptionsPayload | None = None


class PipelineVersionQueryResponse(BaseModel):
    version_id: str
    version: int
    answer: str
    sources: list[RagSourcePayload]
    warnings: list[str] = Field(default_factory=list)
    retrieval: dict[str, Any] = Field(default_factory=dict)


class CitationAnchorPayload(BaseModel):
    citation_id: str
    chunk_id: str
    artifact_id: str
    document_id: str
    document_name: str
    score: float
    snippet: str


class CitationAnchorRequest(BaseModel):
    kb_id: str = Field(min_length=1, max_length=160)
    question: str = Field(min_length=1, max_length=20_000)
    top_k: int = Field(default=4, ge=1, le=50)
    retrieval: RetrievalOptionsPayload | None = None


class CitationAnchorResponse(BaseModel):
    kb_id: str
    citations: list[CitationAnchorPayload]
    citation_count: int


def get_rag_service() -> RagService:
    """Return the process-wide RAG service."""

    global _rag_service
    if _rag_service is None:
        _rag_service = RagService()
    return _rag_service


def set_rag_service_for_tests(service: RagService | None) -> None:
    """Replace the global RAG service in tests."""

    global _rag_service, _pipeline_executor
    _rag_service = service
    _pipeline_executor = None


def configure_pipeline_executor(*, run_registry: Any | None = None) -> KnowledgePipelineExecutor:
    """Configure the process-wide pipeline executor after shared runtime setup."""

    global _pipeline_executor
    _pipeline_executor = KnowledgePipelineExecutor(
        get_rag_service(),
        run_registry=run_registry,
    )
    return _pipeline_executor


def get_pipeline_executor() -> KnowledgePipelineExecutor:
    global _pipeline_executor
    if _pipeline_executor is None:
        _pipeline_executor = KnowledgePipelineExecutor(get_rag_service())
    return _pipeline_executor


def set_pipeline_executor_for_tests(executor: KnowledgePipelineExecutor | None) -> None:
    global _pipeline_executor
    _pipeline_executor = executor


@router.get("/retrieval-capabilities")
async def get_retrieval_capabilities() -> dict[str, Any]:
    return get_rag_service().retrieval_capabilities()


@router.get("/processor-capabilities")
async def get_processor_capabilities() -> dict[str, Any]:
    return get_rag_service().processor_capabilities()


@router.post("/knowledge_bases", response_model=KnowledgeBasePayload)
async def create_knowledge_base(payload: KnowledgeBaseCreateRequest) -> dict[str, Any]:
    try:
        return get_rag_service().create_knowledge_base(payload.name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/knowledge_bases", response_model=KnowledgeBaseListResponse)
async def list_knowledge_bases() -> KnowledgeBaseListResponse:
    return KnowledgeBaseListResponse(
        knowledge_bases=[
            KnowledgeBasePayload.model_validate(item)
            for item in get_rag_service().list_knowledge_bases()
        ]
    )


@router.delete("/knowledge_bases/{kb_id}")
async def delete_knowledge_base(kb_id: str) -> dict[str, bool]:
    try:
        get_rag_service().delete_knowledge_base(kb_id)
        return {"ok": True}
    except KnowledgeBaseNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/knowledge_bases/{kb_id}/documents", response_model=DocumentPayload)
async def upload_document(kb_id: str, file: UploadFile = File(...)) -> dict[str, Any]:
    filename = file.filename or "document.txt"
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="文件过大，请上传 10MB 以内的文档。")

    try:
        return await get_rag_service().upload_document(kb_id, filename, content)
    except KnowledgeBaseNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except UnsupportedDocumentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/knowledge_bases/{kb_id}/documents", response_model=DocumentListResponse)
async def list_documents(kb_id: str) -> DocumentListResponse:
    try:
        return DocumentListResponse(
            documents=[
                DocumentPayload.model_validate(item)
                for item in get_rag_service().list_documents(kb_id)
            ]
        )
    except KnowledgeBaseNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/documents/{doc_id}")
async def delete_document(doc_id: str) -> dict[str, bool]:
    try:
        get_rag_service().delete_document(doc_id)
        return {"ok": True}
    except DocumentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/pipeline/assets", response_model=FileAssetListResponse)
async def list_pipeline_assets(kb_id: str | None = None) -> FileAssetListResponse:
    try:
        assets = get_rag_service().list_pipeline_assets(kb_id=kb_id)
        return FileAssetListResponse(
            assets=[FileAssetPayload.model_validate(item) for item in assets],
            asset_count=len(assets),
        )
    except KnowledgeBaseNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/pipeline/artifacts", response_model=ArtifactListResponse)
async def list_pipeline_artifacts(kb_id: str | None = None) -> ArtifactListResponse:
    try:
        artifacts = get_rag_service().list_pipeline_artifacts(kb_id=kb_id)
        return ArtifactListResponse(
            artifacts=[ArtifactPayload.model_validate(item) for item in artifacts],
            artifact_count=len(artifacts),
        )
    except KnowledgeBaseNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/pipeline/artifacts/{artifact_id}/chunks", response_model=KnowledgeChunkListResponse)
async def list_pipeline_artifact_chunks(artifact_id: str) -> KnowledgeChunkListResponse:
    try:
        chunks = get_rag_service().list_pipeline_artifact_chunks(artifact_id)
        return KnowledgeChunkListResponse(
            artifact_id=artifact_id,
            chunks=[KnowledgeChunkPayload.model_validate(item) for item in chunks],
            chunk_count=len(chunks),
        )
    except DocumentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/pipeline/draft", response_model=PipelineDraftResponse)
async def get_pipeline_draft(kb_id: str) -> PipelineDraftResponse:
    try:
        draft = get_rag_service().get_pipeline_draft(kb_id)
        stages = [
            PipelineDraftStagePayload.model_validate(item)
            for item in draft.get("stages", [])
        ]
        return PipelineDraftResponse(
            kb_id=str(draft["kb_id"]),
            draft_id=str(draft["draft_id"]),
            version=int(draft["version"]),
            updated_at=float(draft["updated_at"]),
            editable=bool(draft["editable"]),
            index_schema_version=int(draft.get("index_schema_version", 2)),
            embedding_profile=dict(draft.get("embedding_profile") or {}),
            retrieval_profile=dict(draft.get("retrieval_profile") or {}),
            stages=stages,
            stage_count=len(stages),
        )
    except KnowledgeBaseNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/pipeline/draft/{kb_id}", response_model=PipelineDraftResponse)
async def update_pipeline_draft(
    kb_id: str,
    payload: PipelineDraftUpdateRequest,
) -> PipelineDraftResponse:
    try:
        draft = get_rag_service().update_pipeline_draft(
            kb_id,
            {
                stage_id: stage_update.model_dump()
                for stage_id, stage_update in payload.stages.items()
            },
            retrieval_profile=(
                payload.retrieval_profile.model_dump(exclude_none=True)
                if payload.retrieval_profile
                else None
            ),
            embedding_profile=payload.embedding_profile,
        )
        stages = [
            PipelineDraftStagePayload.model_validate(item)
            for item in draft.get("stages", [])
        ]
        return PipelineDraftResponse(
            kb_id=str(draft["kb_id"]),
            draft_id=str(draft["draft_id"]),
            version=int(draft["version"]),
            updated_at=float(draft["updated_at"]),
            editable=bool(draft["editable"]),
            index_schema_version=int(draft.get("index_schema_version", 2)),
            embedding_profile=dict(draft.get("embedding_profile") or {}),
            retrieval_profile=dict(draft.get("retrieval_profile") or {}),
            stages=stages,
            stage_count=len(stages),
        )
    except KnowledgeBaseNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PipelineDraftValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/pipeline/draft/{kb_id}/processor-preview",
    response_model=ProcessorPreviewResponse,
)
async def preview_pipeline_processor(
    kb_id: str,
    payload: ProcessorPreviewRequest,
) -> ProcessorPreviewResponse:
    try:
        result = await get_rag_service().preview_pipeline_processor(
            kb_id,
            payload.document_id,
            payload.processor,
        )
        return ProcessorPreviewResponse.model_validate(result)
    except (KnowledgeBaseNotFoundError, DocumentNotFoundError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (PipelineDraftValidationError, ProcessorGenerationError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/pipeline/draft/{kb_id}/preflight", response_model=PipelineDraftPreflightResponse)
async def preflight_pipeline_draft(kb_id: str) -> PipelineDraftPreflightResponse:
    try:
        preflight = get_rag_service().preflight_pipeline_draft(kb_id)
        return PipelineDraftPreflightResponse(
            kb_id=str(preflight["kb_id"]),
            draft_id=str(preflight["draft_id"]),
            ready=bool(preflight["ready"]),
            warnings=list(preflight["warnings"]),
            stage_checks=[
                PipelinePreflightStagePayload.model_validate(item)
                for item in preflight["stage_checks"]
            ],
            document_count=int(preflight["document_count"]),
            artifact_count=int(preflight["artifact_count"]),
            chunk_count=int(preflight["chunk_count"]),
        )
    except KnowledgeBaseNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/pipeline/draft/{kb_id}/execute", response_model=PipelineJobPayload)
async def execute_pipeline_draft(
    kb_id: str,
    payload: PipelineExecuteRequest,
) -> PipelineJobPayload:
    xpert_sources: list[dict[str, Any]] = []
    try:
        if payload.xpert_file_refs:
            try:
                from server.xperts import get_xpert_context_store
            except ModuleNotFoundError:
                from xperts import get_xpert_context_store

            context_store = get_xpert_context_store()
            seen: set[tuple[str, str, str]] = set()
            for reference in payload.xpert_file_refs:
                key = (reference.xpert_id, reference.conversation_id, reference.asset_id)
                if key in seen:
                    continue
                seen.add(key)
                asset = context_store.get_file(
                    reference.xpert_id,
                    reference.asset_id,
                    conversation_id=reference.conversation_id,
                    include_archived=True,
                )
                xpert_sources.append(
                    {
                        "xpert_id": reference.xpert_id,
                        "conversation_id": reference.conversation_id,
                        "asset_id": reference.asset_id,
                        "filename": asset.filename,
                        "text": context_store.read_file_text(asset),
                    }
                )

        job = get_rag_service().create_pipeline_job(
            kb_id,
            draft_version=payload.draft_version,
            source_document_ids=payload.source_document_ids,
            xpert_sources=xpert_sources,
        )
        get_pipeline_executor().notify()
        return PipelineJobPayload.model_validate(job)
    except KnowledgeBaseNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except DocumentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PipelineJobStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except PipelineDraftValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        if exc.__class__.__name__ in {
            "XpertContextNotFoundError",
            "XpertContextValidationError",
        }:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        raise


@router.get("/pipeline/jobs", response_model=PipelineJobListResponse)
async def list_pipeline_jobs(
    kb_id: str | None = None,
    status: str | None = None,
    limit: int = 50,
) -> PipelineJobListResponse:
    valid_statuses = {"queued", "running", "succeeded", "failed", "cancelled"}
    if status is not None and status not in valid_statuses:
        raise HTTPException(status_code=400, detail="Invalid pipeline job status.")
    try:
        jobs = get_rag_service().list_pipeline_jobs(
            kb_id=kb_id,
            status=status,
            limit=limit,
        )
        return PipelineJobListResponse(
            jobs=[PipelineJobPayload.model_validate(item) for item in jobs],
            job_count=len(jobs),
        )
    except KnowledgeBaseNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/pipeline/jobs/{job_id}", response_model=PipelineJobPayload)
async def get_pipeline_job(job_id: str) -> PipelineJobPayload:
    try:
        job = get_rag_service().get_pipeline_job(job_id)
        return PipelineJobPayload.model_validate(get_rag_service().pipeline_job_payload(job))
    except PipelineJobNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/pipeline/jobs/{job_id}/cancel", response_model=PipelineJobPayload)
async def cancel_pipeline_job(job_id: str) -> PipelineJobPayload:
    try:
        job = get_rag_service().request_pipeline_job_cancel(job_id)
        get_pipeline_executor().notify()
        return PipelineJobPayload.model_validate(job)
    except PipelineJobNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PipelineJobStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/pipeline/jobs/{job_id}/retry", response_model=PipelineJobPayload)
async def retry_pipeline_job(job_id: str) -> PipelineJobPayload:
    try:
        job = get_rag_service().retry_pipeline_job(job_id)
        get_pipeline_executor().notify()
        return PipelineJobPayload.model_validate(job)
    except PipelineJobNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PipelineJobStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/pipeline/versions", response_model=PipelineVersionListResponse)
async def list_pipeline_versions(kb_id: str) -> PipelineVersionListResponse:
    try:
        versions = get_rag_service().list_pipeline_versions(kb_id)
        active = next((item["version_id"] for item in versions if item["active"]), None)
        return PipelineVersionListResponse(
            versions=[PipelineVersionPayload.model_validate(item) for item in versions],
            version_count=len(versions),
            active_version_id=active,
        )
    except KnowledgeBaseNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/pipeline/versions/{version_id}", response_model=PipelineVersionPayload)
async def get_pipeline_version(version_id: str) -> PipelineVersionPayload:
    try:
        version = get_rag_service().get_pipeline_version(version_id)
        active = get_rag_service().get_active_pipeline_version(str(version["kb_id"]))
        return PipelineVersionPayload.model_validate(
            get_rag_service().pipeline_version_payload(
                version,
                active_id=active["version_id"] if active else None,
            )
        )
    except PipelineVersionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "/pipeline/versions/{version_id}/query",
    response_model=PipelineVersionQueryResponse,
)
async def query_pipeline_version(
    version_id: str,
    payload: PipelineVersionQueryRequest,
) -> PipelineVersionQueryResponse:
    try:
        result = await get_rag_service().query_pipeline_version(
            version_id,
            payload.question,
            top_k=payload.top_k,
            retrieval=(
                payload.retrieval.model_dump(exclude_none=True)
                if payload.retrieval
                else None
            ),
        )
        version = get_rag_service().get_pipeline_version(version_id)
        await get_pipeline_executor().record_job_event(
            str(version["job_id"]),
            event_type="knowledge_pipeline.version_previewed",
            title="Candidate index previewed",
            summary=f"Preview returned {len(result.get('sources', []))} sources.",
            metadata={"version_id": version_id, "source_count": len(result.get("sources", []))},
        )
        return PipelineVersionQueryResponse.model_validate(result)
    except PipelineVersionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/pipeline/versions/{version_id}/activate", response_model=PipelineVersionPayload)
async def activate_pipeline_version(version_id: str) -> PipelineVersionPayload:
    try:
        version = get_rag_service().activate_pipeline_version(version_id)
        stored = get_rag_service().get_pipeline_version(version_id)
        await get_pipeline_executor().record_job_event(
            str(stored["job_id"]),
            event_type="knowledge_pipeline.version_activated",
            title="Knowledge index activated",
            summary=f"Version v{version['version']} is now active.",
            metadata={"version_id": version_id, "version": version["version"]},
        )
        return PipelineVersionPayload.model_validate(version)
    except PipelineVersionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/pipeline/citations", response_model=CitationAnchorResponse)
async def create_pipeline_citations(payload: CitationAnchorRequest) -> CitationAnchorResponse:
    try:
        citations = await get_rag_service().create_pipeline_citations(
            payload.kb_id,
            payload.question,
            top_k=payload.top_k,
            retrieval=(
                payload.retrieval.model_dump(exclude_none=True)
                if payload.retrieval
                else None
            ),
        )
        return CitationAnchorResponse(
            kb_id=payload.kb_id,
            citations=[CitationAnchorPayload.model_validate(item) for item in citations],
            citation_count=len(citations),
        )
    except KnowledgeBaseNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/query", response_model=RagQueryResponse)
async def query_knowledge_base(payload: RagQueryRequest) -> RagQueryResponse:
    try:
        result = await get_rag_service().query(
            payload.kb_id,
            payload.question,
            top_k=payload.top_k,
            retrieval=(
                payload.retrieval.model_dump(exclude_none=True)
                if payload.retrieval
                else None
            ),
        )
        return RagQueryResponse.model_validate(result)
    except KnowledgeBaseNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
