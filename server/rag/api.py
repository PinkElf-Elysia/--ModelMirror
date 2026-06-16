from __future__ import annotations

from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from .rag_service import (
    DocumentNotFoundError,
    KnowledgeBaseNotFoundError,
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
