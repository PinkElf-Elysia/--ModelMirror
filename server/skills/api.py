from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .skill_manager import (
    InstalledSkill,
    SkillInstallError,
    SkillManager,
    SkillManagerError,
    SkillNotFoundError,
    SkillValidationError,
)


router = APIRouter(prefix="/api/skills", tags=["skills"])
_skill_manager: SkillManager | None = None


class SkillInstallRequest(BaseModel):
    repo_url: str = Field(min_length=1, max_length=500)
    sub_path: str = Field(default="", max_length=260)


class SkillPayload(BaseModel):
    skill_id: str
    name: str
    description: str
    repo_url: str
    sub_path: str
    installed_at: float


class InstalledSkillsResponse(BaseModel):
    skills: list[SkillPayload]


class SkillContentResponse(BaseModel):
    skill_id: str
    content: str


def get_skill_manager() -> SkillManager:
    """Return the process-wide Skill manager."""

    global _skill_manager
    if _skill_manager is None:
        _skill_manager = SkillManager()
    return _skill_manager


def set_skill_manager_for_tests(manager: SkillManager | None) -> None:
    """Replace the global Skill manager in tests."""

    global _skill_manager
    _skill_manager = manager


def _payload_from_skill(skill: InstalledSkill) -> SkillPayload:
    return SkillPayload(
        skill_id=skill.skill_id,
        name=skill.name,
        description=skill.description,
        repo_url=skill.repo_url,
        sub_path=skill.sub_path,
        installed_at=skill.installed_at,
    )


@router.get("/installed", response_model=InstalledSkillsResponse)
async def list_installed_skills() -> InstalledSkillsResponse:
    skills = await asyncio.to_thread(get_skill_manager().list_installed_skills)
    return InstalledSkillsResponse(
        skills=[_payload_from_skill(skill) for skill in skills]
    )


@router.post("/install", response_model=SkillPayload)
async def install_skill(payload: SkillInstallRequest) -> SkillPayload:
    try:
        skill = await asyncio.to_thread(
            get_skill_manager().install_skill,
            payload.repo_url,
            payload.sub_path,
        )
        return _payload_from_skill(skill)
    except SkillValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except SkillInstallError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except SkillManagerError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.delete("/{skill_id}")
async def uninstall_skill(skill_id: str) -> dict[str, bool]:
    try:
        await asyncio.to_thread(get_skill_manager().uninstall_skill, skill_id)
        return {"ok": True}
    except SkillNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SkillValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{skill_id}/content", response_model=SkillContentResponse)
async def get_skill_content(skill_id: str) -> SkillContentResponse:
    try:
        content = await asyncio.to_thread(
            get_skill_manager().get_skill_content,
            skill_id,
        )
        return SkillContentResponse(skill_id=skill_id, content=content)
    except SkillNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SkillValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

