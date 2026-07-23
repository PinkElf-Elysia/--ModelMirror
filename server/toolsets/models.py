from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


ToolsetStatus = Literal["draft", "published", "archived"]
MCPTransport = Literal["stdio", "streamable_http", "legacy_sse"]
MCPNetworkPolicy = Literal["public_only", "trusted_private"]


class SecretBinding(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    credential_id: str = Field(min_length=1, max_length=160)


class MCPConnectionProfile(BaseModel):
    transport: MCPTransport = "stdio"
    command: list[str] = Field(default_factory=list, max_length=64)
    url: str = Field(default="", max_length=2048)
    headers: list[SecretBinding] = Field(default_factory=list, max_length=40)
    environment: list[SecretBinding] = Field(default_factory=list, max_length=40)
    installed_project_id: str = Field(default="", max_length=160)
    working_directory: str = Field(default="", max_length=500)
    auto_start: bool = False
    auto_reconnect: bool = True
    reconnect_attempts: int = Field(default=2, ge=0, le=5)
    tool_prefix: str = Field(
        default="",
        max_length=80,
        pattern=r"^$|^[A-Za-z_][A-Za-z0-9_]{0,79}$",
    )
    network_policy: MCPNetworkPolicy = "public_only"
    timeout_seconds: int = Field(default=30, ge=5, le=300)


class ToolDefinition(BaseModel):
    original_name: str = Field(min_length=1, max_length=200)
    alias: str = Field(default="", max_length=200)
    description: str = Field(default="", max_length=4000)
    input_schema: dict[str, Any] = Field(default_factory=dict)
    default_arguments: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = False
    order: int = Field(default=0, ge=0, le=10_000)
    schema_hash: str = Field(default="", max_length=128)
    discovered_at: float = 0.0

    @property
    def raw_name(self) -> str:
        return self.original_name

    @property
    def exposed_name(self) -> str:
        return self.alias.strip() or self.original_name

    @property
    def exposed_description(self) -> str:
        return self.description


class ToolsetVersion(BaseModel):
    version: int = Field(ge=1)
    draft_revision: int = Field(ge=1)
    connection: MCPConnectionProfile
    tools: list[ToolDefinition] = Field(default_factory=list)
    schema_hash: str
    release_notes: str = Field(default="", max_length=2000)
    published_at: float


class ToolsetDefinition(BaseModel):
    id: str
    name: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=4000)
    tags: list[str] = Field(default_factory=list, max_length=30)
    privacy_policy: str = Field(default="", max_length=4000)
    disclaimer: str = Field(default="", max_length=4000)
    status: ToolsetStatus = "draft"
    revision: int = Field(default=1, ge=1)
    published_version: int | None = None
    connection: MCPConnectionProfile = Field(default_factory=MCPConnectionProfile)
    tools: list[ToolDefinition] = Field(default_factory=list)
    versions: list[ToolsetVersion] = Field(default_factory=list)
    runtime_status: str = "disconnected"
    runtime_session_id: str | None = None
    runtime_error: str = ""
    created_at: float
    updated_at: float


class CredentialRecord(BaseModel):
    credential_id: str
    name: str = Field(min_length=1, max_length=160)
    kind: Literal["header", "environment", "provider_key", "generic"] = "generic"
    prefix: str = ""
    masked_value: str = ""
    ciphertext: str
    status: Literal["active", "unavailable", "revoked"] = "active"
    created_at: float
    updated_at: float
