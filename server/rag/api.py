from __future__ import annotations

from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from .rag_service import (
    DocumentNotFoundError,
    KnowledgeBaseNotFoundError,
    PipelineDraftValidationError,
    RagService,
    UnsupportedDocumentError,
)


MAX_UPLOAD_BYTES = 10 * 1024 * 1024

router = APIRouter(prefix="/api/rag", tags=["rag"])
_rag_service: RagService | None = None


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


class RagQueryRequest(BaseModel):
    kb_id: str = Field(min_length=1, max_length=160)
    question: str = Field(min_length=1, max_length=20_000)
    top_k: int = Field(default=4, ge=1, le=10)


class RagQueryResponse(BaseModel):
    answer: str
    sources: list[RagSourcePayload]


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
    stages: list[PipelineDraftStagePayload]
    stage_count: int


class PipelineDraftStageUpdate(BaseModel):
    config: dict[str, Any] = Field(default_factory=dict)


class PipelineDraftUpdateRequest(BaseModel):
    stages: dict[str, PipelineDraftStageUpdate] = Field(default_factory=dict)


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
    top_k: int = Field(default=4, ge=1, le=10)


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

    global _rag_service
    _rag_service = service


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
            stages=stages,
            stage_count=len(stages),
        )
    except KnowledgeBaseNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PipelineDraftValidationError as exc:
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


@router.post("/pipeline/citations", response_model=CitationAnchorResponse)
async def create_pipeline_citations(payload: CitationAnchorRequest) -> CitationAnchorResponse:
    try:
        citations = await get_rag_service().create_pipeline_citations(
            payload.kb_id,
            payload.question,
            top_k=payload.top_k,
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
        )
        return RagQueryResponse.model_validate(result)
    except KnowledgeBaseNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
