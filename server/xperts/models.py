from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

try:
    from server.workflow_native.schemas import NativeWorkflowDefinition, ValidationIssue
except ModuleNotFoundError:
    from workflow_native.schemas import NativeWorkflowDefinition, ValidationIssue


XpertStatus = Literal["draft", "published", "archived"]


class XpertAgentConfig(BaseModel):
    max_concurrency: int = Field(default=4, ge=1, le=100)
    recursion_limit: int = Field(default=1000, ge=100, le=10_000)


class XpertDraft(BaseModel):
    workflow: NativeWorkflowDefinition
    input_variable: str = Field(default="user_input", min_length=1, max_length=128)
    history_variable: str = Field(
        default="conversation_history",
        min_length=1,
        max_length=128,
    )
    output_variable: str = Field(default="agent_output", min_length=1, max_length=128)
    agent_config: XpertAgentConfig = Field(default_factory=XpertAgentConfig)


class XpertVersion(BaseModel):
    version: int = Field(ge=1)
    draft_revision: int = Field(ge=1)
    workflow: NativeWorkflowDefinition
    input_variable: str
    history_variable: str
    output_variable: str
    # Legacy versions intentionally keep the old unlimited runtime behavior.
    agent_config: XpertAgentConfig | None = None
    release_notes: str = ""
    checksum: str
    published_at: float


class XpertDefinition(BaseModel):
    id: str
    slug: str
    name: str
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    starters: list[str] = Field(default_factory=list)
    status: XpertStatus = "draft"
    draft_revision: int = Field(default=1, ge=1)
    published_version: int | None = None
    draft: XpertDraft
    versions: list[XpertVersion] = Field(default_factory=list)
    created_at: float
    updated_at: float


class XpertSummary(BaseModel):
    id: str
    slug: str
    name: str
    description: str
    tags: list[str]
    starters: list[str]
    status: XpertStatus
    draft_revision: int
    published_version: int | None
    version_count: int
    created_at: float
    updated_at: float


class XpertValidationResult(BaseModel):
    valid: bool
    issues: list[ValidationIssue] = Field(default_factory=list)
    order: list[str] = Field(default_factory=list)
    node_count: int
    edge_count: int


class XpertConversationMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=20_000)


class XpertRunRequest(BaseModel):
    message: str = Field(min_length=1, max_length=20_000)
    messages: list[XpertConversationMessage] = Field(default_factory=list, max_length=20)
    version: int | None = Field(default=None, ge=1)
    conversation_id: str | None = Field(default=None, max_length=200)
    file_asset_ids: list[str] = Field(default_factory=list, max_length=5)
