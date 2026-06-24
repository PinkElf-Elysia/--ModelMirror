from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class MetaAgentGenerateRequest(BaseModel):
    goal: str = Field(min_length=10, max_length=20_000)
    model_id: str = Field(default="deepseek/deepseek-chat", min_length=1, max_length=256)
    temperature: float = Field(default=0.3, ge=0, le=2)
    max_tasks: int = Field(default=5, ge=1, le=8)


class MetaAgentParameter(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    type: str = Field(default="string", max_length=40)
    description: str = Field(default="", max_length=1000)
    required: bool = True


class MetaAgentGeneratedAgent(BaseModel):
    name: str = Field(default="", max_length=120)
    description: str = Field(default="", max_length=1000)
    prompt: str = Field(default="", max_length=20_000)
    tool_names: list[str] | None = Field(default=None, max_length=16)


class MetaAgentSubTask(BaseModel):
    name: str = Field(min_length=1, max_length=96)
    description: str = Field(min_length=1, max_length=1600)
    reason: str | None = Field(default=None, max_length=1600)
    inputs: list[MetaAgentParameter] = Field(default_factory=list, max_length=16)
    outputs: list[MetaAgentParameter] = Field(default_factory=list, max_length=16)
    agent: MetaAgentGeneratedAgent | None = None
    agents: list[MetaAgentGeneratedAgent] | None = Field(default=None, max_length=4)


class MetaAgentPlan(BaseModel):
    thought: str = Field(default="", max_length=4000)
    sub_tasks: list[MetaAgentSubTask] = Field(default_factory=list, max_length=8)


class MetaAgentGenerateResponse(BaseModel):
    goal: str
    plan: MetaAgentPlan
    workflow: dict[str, Any]
    warnings: list[str] = Field(default_factory=list)
    validation: dict[str, Any]
