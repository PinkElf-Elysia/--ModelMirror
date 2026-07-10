from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

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


router = APIRouter(prefix="/api/xperts", tags=["xperts"])
_xpert_store: XpertStore | None = None


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


def get_xpert_store() -> XpertStore:
    global _xpert_store
    if _xpert_store is None:
        _xpert_store = XpertStore()
    return _xpert_store


def set_xpert_store_for_tests(store: XpertStore | None) -> None:
    global _xpert_store
    _xpert_store = store


def _raise_store_error(exc: Exception) -> None:
    if isinstance(exc, XpertNotFoundError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, XpertValidationError):
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if isinstance(exc, XpertConflictError):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    raise HTTPException(status_code=500, detail=str(exc)) from exc


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
        return validate_xpert_definition(xpert)
    except XpertStoreError as exc:
        _raise_store_error(exc)


@router.post("/{xpert_id}/publish", response_model=XpertVersion)
async def publish_xpert(xpert_id: str, payload: XpertPublishRequest) -> XpertVersion:
    try:
        store = get_xpert_store()
        xpert = await asyncio.to_thread(store.get_xpert, xpert_id)
        validation = validate_xpert_definition(xpert)
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
