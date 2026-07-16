from __future__ import annotations

import asyncio
import re

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field

from .context import (
    MAX_FILE_BYTES,
    CandidateStatus,
    MemoryScope,
    XpertContextError,
    XpertContextNotFoundError,
    XpertContextStore,
    XpertContextValidationError,
)

from .models import (
    XpertDefinition,
    XpertDraft,
    XpertStatus,
    XpertSummary,
    XpertValidationResult,
    XpertVersion,
)
from .store import (
    XpertConflictError,
    XpertNotFoundError,
    XpertStore,
    XpertStoreError,
    XpertValidationError,
)
from .validation import validate_xpert_definition

try:
    from server.skills.api import get_skill_manager
    from server.workflow_native.schemas import ValidationIssue
except ModuleNotFoundError:
    from skills.api import get_skill_manager
    from workflow_native.schemas import ValidationIssue


router = APIRouter(prefix="/api/xperts", tags=["xperts"])
_xpert_store: XpertStore | None = None
_xpert_context_store: XpertContextStore | None = None


def _validate_installed_skills(
    xpert: XpertDefinition,
    validation: XpertValidationResult,
) -> XpertValidationResult:
    installed = {
        item.skill_id for item in get_skill_manager().list_installed_skills()
    }
    issues = list(validation.issues)
    for node in xpert.draft.workflow.nodes:
        data = node.data if isinstance(node.data, dict) else {}
        if str(data.get("runtimeMiddlewareId") or "") != "skills_runtime":
            continue
        config = data.get("runtimeMiddlewareConfig") or {}
        if str(config.get("auto_discover", False)).lower() in {"true", "1", "yes"}:
            continue
        skill_ids = {
            value.strip()
            for value in re.split(r"[,\n]+", str(config.get("skill_ids") or ""))
            if value.strip()
        }
        missing = sorted(skill_ids - installed)
        if missing:
            issues.append(
                ValidationIssue(
                    code="xpert_skills_not_installed",
                    message=f"Install referenced Skills before publish: {', '.join(missing)}.",
                    node_id=node.id,
                )
            )
    return validation.model_copy(
        update={
            "valid": not any(issue.severity == "error" for issue in issues),
            "issues": issues,
        }
    )


class XpertCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    slug: str | None = Field(default=None, max_length=64)
    description: str = Field(default="", max_length=2000)
    tags: list[str] = Field(default_factory=list, max_length=20)
    starters: list[str] = Field(default_factory=list, max_length=8)


class XpertUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    tags: list[str] | None = Field(default=None, max_length=20)
    starters: list[str] | None = Field(default=None, max_length=8)
    status: XpertStatus | None = None
    draft: XpertDraft | None = None


class XpertPublishRequest(BaseModel):
    release_notes: str = Field(default="", max_length=2000)


class XpertListResponse(BaseModel):
    version: str = "xpert-definition-v1"
    items: list[XpertSummary]
    total: int


class XpertConversationCreateRequest(BaseModel):
    title: str = Field(default="", max_length=120)


class XpertMemoryCreateRequest(BaseModel):
    content: str = Field(min_length=1, max_length=4000)
    scope: MemoryScope = "xpert"
    conversation_id: str | None = Field(default=None, max_length=200)
    tags: list[str] = Field(default_factory=list, max_length=10)
    source_type: str = Field(default="user", max_length=80)
    source_id: str | None = Field(default=None, max_length=200)


def get_xpert_store() -> XpertStore:
    global _xpert_store
    if _xpert_store is None:
        _xpert_store = XpertStore()
    return _xpert_store


def set_xpert_store_for_tests(store: XpertStore | None) -> None:
    global _xpert_store
    _xpert_store = store


def get_xpert_context_store() -> XpertContextStore:
    global _xpert_context_store
    if _xpert_context_store is None:
        _xpert_context_store = XpertContextStore()
    return _xpert_context_store


def set_xpert_context_store_for_tests(store: XpertContextStore | None) -> None:
    global _xpert_context_store
    _xpert_context_store = store


def _raise_store_error(exc: Exception) -> None:
    if isinstance(exc, XpertNotFoundError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, XpertValidationError):
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if isinstance(exc, XpertConflictError):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    raise HTTPException(status_code=500, detail=str(exc)) from exc


def _raise_context_error(exc: Exception) -> None:
    if isinstance(exc, XpertContextNotFoundError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, XpertContextValidationError):
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    raise HTTPException(status_code=500, detail=str(exc)) from exc


async def _ensure_xpert_exists(xpert_id: str) -> None:
    try:
        await asyncio.to_thread(get_xpert_store().get_xpert, xpert_id)
    except XpertStoreError as exc:
        _raise_store_error(exc)


@router.get("", response_model=XpertListResponse)
async def list_xperts(
    status: XpertStatus | None = None,
    search: str = Query(default="", max_length=200),
    limit: int = Query(default=50, ge=1, le=200),
) -> XpertListResponse:
    try:
        items = await asyncio.to_thread(
            get_xpert_store().list_xperts,
            status=status,
            search=search,
            limit=limit,
        )
        return XpertListResponse(items=items, total=len(items))
    except XpertStoreError as exc:
        _raise_store_error(exc)


@router.post("", response_model=XpertDefinition)
async def create_xpert(payload: XpertCreateRequest) -> XpertDefinition:
    try:
        return await asyncio.to_thread(
            get_xpert_store().create_xpert,
            name=payload.name,
            slug=payload.slug,
            description=payload.description,
            tags=payload.tags,
            starters=payload.starters,
        )
    except XpertStoreError as exc:
        _raise_store_error(exc)


@router.get("/{xpert_id}", response_model=XpertDefinition)
async def get_xpert(xpert_id: str) -> XpertDefinition:
    try:
        return await asyncio.to_thread(get_xpert_store().get_xpert, xpert_id)
    except XpertStoreError as exc:
        _raise_store_error(exc)


@router.patch("/{xpert_id}", response_model=XpertDefinition)
async def update_xpert(xpert_id: str, payload: XpertUpdateRequest) -> XpertDefinition:
    try:
        return await asyncio.to_thread(
            get_xpert_store().update_xpert,
            xpert_id,
            payload.model_dump(exclude_unset=True, mode="json"),
        )
    except XpertStoreError as exc:
        _raise_store_error(exc)


@router.post("/{xpert_id}/validate", response_model=XpertValidationResult)
async def validate_xpert(xpert_id: str) -> XpertValidationResult:
    try:
        xpert = await asyncio.to_thread(get_xpert_store().get_xpert, xpert_id)
        return _validate_installed_skills(xpert, validate_xpert_definition(xpert))
    except XpertStoreError as exc:
        _raise_store_error(exc)


@router.post("/{xpert_id}/publish", response_model=XpertVersion)
async def publish_xpert(xpert_id: str, payload: XpertPublishRequest) -> XpertVersion:
    try:
        store = get_xpert_store()
        xpert = await asyncio.to_thread(store.get_xpert, xpert_id)
        validation = _validate_installed_skills(
            xpert, validate_xpert_definition(xpert)
        )
        if not validation.valid:
            raise HTTPException(
                status_code=422,
                detail={
                    "message": "Xpert publish preflight failed.",
                    "issues": [issue.model_dump(mode="json") for issue in validation.issues],
                },
            )
        return await asyncio.to_thread(
            store.publish_xpert,
            xpert_id,
            release_notes=payload.release_notes,
            expected_revision=xpert.draft_revision,
        )
    except HTTPException:
        raise
    except XpertStoreError as exc:
        _raise_store_error(exc)


@router.get("/{xpert_id}/versions", response_model=list[XpertVersion])
async def list_xpert_versions(xpert_id: str) -> list[XpertVersion]:
    try:
        return await asyncio.to_thread(get_xpert_store().list_versions, xpert_id)
    except XpertStoreError as exc:
        _raise_store_error(exc)


@router.get("/{xpert_id}/versions/{version}", response_model=XpertVersion)
async def get_xpert_version(xpert_id: str, version: int) -> XpertVersion:
    try:
        return await asyncio.to_thread(get_xpert_store().get_version, xpert_id, version)
    except XpertStoreError as exc:
        _raise_store_error(exc)


@router.post("/{xpert_id}/conversations")
async def create_xpert_conversation(
    xpert_id: str,
    payload: XpertConversationCreateRequest,
) -> dict:
    await _ensure_xpert_exists(xpert_id)
    try:
        item = await asyncio.to_thread(
            get_xpert_context_store().create_conversation,
            xpert_id,
            title=payload.title,
        )
        return get_xpert_context_store().conversation_payload(item, include_messages=True)
    except XpertContextError as exc:
        _raise_context_error(exc)


@router.get("/{xpert_id}/conversations")
async def list_xpert_conversations(
    xpert_id: str,
    limit: int = Query(default=50, ge=1, le=200),
) -> dict:
    await _ensure_xpert_exists(xpert_id)
    try:
        store = get_xpert_context_store()
        items = await asyncio.to_thread(store.list_conversations, xpert_id, limit=limit)
        return {
            "version": "xpert-conversation-v1",
            "items": [store.conversation_payload(item, include_messages=False) for item in items],
            "total": len(items),
        }
    except XpertContextError as exc:
        _raise_context_error(exc)


@router.get("/{xpert_id}/conversations/{conversation_id}")
async def get_xpert_conversation(xpert_id: str, conversation_id: str) -> dict:
    await _ensure_xpert_exists(xpert_id)
    try:
        store = get_xpert_context_store()
        item = await asyncio.to_thread(store.get_conversation, xpert_id, conversation_id)
        return store.conversation_payload(item, include_messages=True)
    except XpertContextError as exc:
        _raise_context_error(exc)


@router.post("/{xpert_id}/conversations/{conversation_id}/files")
async def upload_xpert_conversation_file(
    xpert_id: str,
    conversation_id: str,
    file: UploadFile = File(...),
) -> dict:
    await _ensure_xpert_exists(xpert_id)
    content = await file.read(MAX_FILE_BYTES + 1)
    try:
        store = get_xpert_context_store()
        item = await asyncio.to_thread(
            store.add_file,
            xpert_id,
            conversation_id,
            filename=file.filename or "",
            content=content,
        )
        return store.file_payload(item)
    except XpertContextError as exc:
        _raise_context_error(exc)
    finally:
        await file.close()


@router.get("/{xpert_id}/conversations/{conversation_id}/files")
async def list_xpert_conversation_files(
    xpert_id: str,
    conversation_id: str,
    include_archived: bool = False,
) -> dict:
    await _ensure_xpert_exists(xpert_id)
    try:
        store = get_xpert_context_store()
        items = await asyncio.to_thread(
            store.list_files,
            xpert_id,
            conversation_id,
            include_archived=include_archived,
        )
        return {"items": [store.file_payload(item) for item in items], "total": len(items)}
    except XpertContextError as exc:
        _raise_context_error(exc)


@router.delete("/{xpert_id}/conversations/{conversation_id}/files/{asset_id}")
async def archive_xpert_conversation_file(
    xpert_id: str,
    conversation_id: str,
    asset_id: str,
) -> dict:
    await _ensure_xpert_exists(xpert_id)
    try:
        store = get_xpert_context_store()
        item = await asyncio.to_thread(
            store.archive_file,
            xpert_id,
            conversation_id,
            asset_id,
        )
        return store.file_payload(item)
    except XpertContextError as exc:
        _raise_context_error(exc)


@router.get("/{xpert_id}/memories")
async def list_xpert_memories(
    xpert_id: str,
    scope: str = Query(default="both", pattern="^(conversation|xpert|both)$"),
    conversation_id: str | None = None,
    search: str = Query(default="", max_length=500),
    limit: int = Query(default=50, ge=1, le=200),
) -> dict:
    await _ensure_xpert_exists(xpert_id)
    try:
        store = get_xpert_context_store()
        items = await asyncio.to_thread(
            store.list_memories,
            xpert_id,
            scope=scope,
            conversation_id=conversation_id,
            search=search,
            limit=limit,
        )
        return {"items": [store.memory_payload(item) for item in items], "total": len(items)}
    except XpertContextError as exc:
        _raise_context_error(exc)


@router.post("/{xpert_id}/memories")
async def create_xpert_memory(xpert_id: str, payload: XpertMemoryCreateRequest) -> dict:
    await _ensure_xpert_exists(xpert_id)
    try:
        store = get_xpert_context_store()
        item = await asyncio.to_thread(
            store.create_memory,
            xpert_id,
            content=payload.content,
            scope=payload.scope,
            conversation_id=payload.conversation_id,
            tags=payload.tags,
            source_type=payload.source_type,
            source_id=payload.source_id,
        )
        return store.memory_payload(item)
    except XpertContextError as exc:
        _raise_context_error(exc)


@router.delete("/{xpert_id}/memories/{memory_id}")
async def archive_xpert_memory(xpert_id: str, memory_id: str) -> dict:
    await _ensure_xpert_exists(xpert_id)
    try:
        store = get_xpert_context_store()
        item = await asyncio.to_thread(store.archive_memory, xpert_id, memory_id)
        return store.memory_payload(item)
    except XpertContextError as exc:
        _raise_context_error(exc)


@router.get("/{xpert_id}/memory-candidates")
async def list_xpert_memory_candidates(
    xpert_id: str,
    status: CandidateStatus | None = None,
    conversation_id: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
) -> dict:
    await _ensure_xpert_exists(xpert_id)
    try:
        store = get_xpert_context_store()
        items = await asyncio.to_thread(
            store.list_candidates,
            xpert_id,
            status=status,
            conversation_id=conversation_id,
            limit=limit,
        )
        return {"items": [store.candidate_payload(item) for item in items], "total": len(items)}
    except XpertContextError as exc:
        _raise_context_error(exc)


@router.post("/{xpert_id}/memory-candidates/{candidate_id}/approve")
async def approve_xpert_memory_candidate(xpert_id: str, candidate_id: str) -> dict:
    await _ensure_xpert_exists(xpert_id)
    try:
        store = get_xpert_context_store()
        item = await asyncio.to_thread(
            store.decide_candidate,
            xpert_id,
            candidate_id,
            approve=True,
        )
        return store.candidate_payload(item)
    except XpertContextError as exc:
        _raise_context_error(exc)


@router.post("/{xpert_id}/memory-candidates/{candidate_id}/reject")
async def reject_xpert_memory_candidate(xpert_id: str, candidate_id: str) -> dict:
    await _ensure_xpert_exists(xpert_id)
    try:
        store = get_xpert_context_store()
        item = await asyncio.to_thread(
            store.decide_candidate,
            xpert_id,
            candidate_id,
            approve=False,
        )
        return store.candidate_payload(item)
    except XpertContextError as exc:
        _raise_context_error(exc)
