from __future__ import annotations

import asyncio
import hashlib
import json
from copy import deepcopy
from typing import Any, Awaitable, Callable

from jsonschema import Draft202012Validator

try:
    from server.mcp.manager import MCPClientManager
    from server.xpert_runtime.toolset import (
        RuntimeTool,
        RuntimeToolCall,
        RuntimeToolError,
        RuntimeToolResult,
    )
except ModuleNotFoundError:  # Docker copies server packages directly under /app.
    from mcp.manager import MCPClientManager
    from xpert_runtime.toolset import (
        RuntimeTool,
        RuntimeToolCall,
        RuntimeToolError,
        RuntimeToolResult,
    )

from .credentials import CredentialStore
from .models import (
    MCPConnectionProfile,
    ToolDefinition,
    ToolsetDefinition,
    ToolsetVersion,
)
from .store import (
    ToolsetNotFoundError,
    ToolsetStore,
    ToolsetValidationError,
)


ToolTestRunner = Callable[[RuntimeToolCall], Awaitable[RuntimeToolResult]]
InstalledProjectResolver = Callable[[str], dict[str, Any] | None]


def _schema_hash(schema: dict[str, Any]) -> str:
    encoded = json.dumps(
        schema,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class ToolsetService:
    def __init__(
        self,
        store: ToolsetStore,
        credentials: CredentialStore,
        mcp_manager: MCPClientManager,
        installed_project_resolver: InstalledProjectResolver | None = None,
    ) -> None:
        self.store = store
        self.credentials = credentials
        self.mcp_manager = mcp_manager
        self.installed_project_resolver = installed_project_resolver
        self._draft_sessions: dict[str, str] = {}
        self._version_sessions: dict[tuple[str, int], str] = {}
        self._version_warnings: dict[tuple[str, int], list[str]] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._tool_test_runner: ToolTestRunner | None = None

    def set_tool_test_runner(self, runner: ToolTestRunner) -> None:
        self._tool_test_runner = runner

    async def connect(self, toolset_id: str) -> ToolsetDefinition:
        lock = self._locks.setdefault(toolset_id, asyncio.Lock())
        async with lock:
            item = self.store.get_toolset(toolset_id)
            existing = self._draft_sessions.pop(toolset_id, None)
            if existing:
                await self._safe_disconnect(existing)
            session_id: str | None = None
            try:
                session_id = await self._connect_profile(item.connection)
                raw_tools = await self.mcp_manager.list_tools(session_id)
                tools = [_normalize_tool(tool) for tool in raw_tools]
                updated = self.store.replace_discovered_tools(
                    toolset_id,
                    tools=tools,
                )
                updated = self.store.set_runtime_state(
                    toolset_id,
                    status="connected",
                    session_id=session_id,
                )
                self._draft_sessions[toolset_id] = session_id
                return updated
            except Exception as exc:
                if session_id:
                    await self._safe_disconnect(session_id)
                self.store.set_runtime_state(
                    toolset_id,
                    status="error",
                    session_id=None,
                    error=str(exc),
                )
                raise

    async def disconnect(self, toolset_id: str) -> ToolsetDefinition:
        self.store.get_toolset(toolset_id)
        session_id = self._draft_sessions.pop(toolset_id, None)
        if session_id:
            await self._safe_disconnect(session_id)
        return self.store.set_runtime_state(
            toolset_id,
            status="disconnected",
            session_id=None,
        )

    async def publish(
        self,
        toolset_id: str,
        *,
        expected_revision: int,
        release_notes: str = "",
    ) -> ToolsetVersion:
        item = self.store.get_toolset(toolset_id)
        connection = self._resolve_installed_project(item.connection)
        return self.store.publish(
            toolset_id,
            revision=expected_revision,
            release_notes=release_notes,
            connection_override=connection,
        )

    async def test_tool(
        self,
        toolset_id: str,
        raw_name: str,
        arguments: dict[str, Any],
    ) -> RuntimeToolResult:
        item = self.store.get_toolset(toolset_id)
        tool = next((row for row in item.tools if row.raw_name == raw_name), None)
        if tool is None:
            raise ToolsetNotFoundError(f"Tool not found: {raw_name}")
        session_id = self._draft_sessions.get(toolset_id)
        if not session_id:
            raise ToolsetValidationError("Connect the Toolset before testing a tool.")
        merged = {**deepcopy(tool.default_arguments), **dict(arguments)}
        _validate_arguments(tool, merged)
        call = RuntimeToolCall(
            tool_name=tool.exposed_name,
            arguments=merged,
            metadata={
                "toolset_test": True,
                "toolset_id": toolset_id,
                "toolset_raw_name": raw_name,
                "toolset_session_id": session_id,
            },
        )
        if self._tool_test_runner is not None:
            return await self._tool_test_runner(call)
        result = await self.mcp_manager.call_tool(session_id, raw_name, merged)
        return _normalize_result(result, toolset_id=toolset_id, version=None)

    async def autostart(self) -> list[str]:
        warnings: list[str] = []
        for item in self.store.list_toolsets(status="published"):
            if not item.connection.auto_start or item.published_version is None:
                continue
            try:
                await self.ensure_version_session(item.id, item.published_version)
            except Exception as exc:
                warnings.append(f"{item.id}: {str(exc)[:300]}")
        return warnings

    async def close(self) -> None:
        session_ids = set(self._draft_sessions.values()) | set(
            self._version_sessions.values()
        )
        self._draft_sessions.clear()
        self._version_sessions.clear()
        self._version_warnings.clear()
        for session_id in session_ids:
            await self._safe_disconnect(session_id)

    async def ensure_version_session(self, toolset_id: str, version: int) -> str:
        key = (toolset_id, version)
        existing = self._version_sessions.get(key)
        if existing:
            try:
                snapshot = self.store.get_version(toolset_id, version)
                discovered = {
                    tool.name: tool
                    for tool in await self.mcp_manager.list_tools(existing)
                }
                hard_errors, warnings = _detect_schema_drift(snapshot, discovered)
                if hard_errors:
                    raise ToolsetValidationError("; ".join(hard_errors))
                self._version_warnings[key] = warnings
                return existing
            except Exception:
                self._version_sessions.pop(key, None)
                self._version_warnings.pop(key, None)
                await self._safe_disconnect(existing)
        lock = self._locks.setdefault(f"{toolset_id}@{version}", asyncio.Lock())
        async with lock:
            existing = self._version_sessions.get(key)
            if existing:
                return existing
            snapshot = self.store.get_version(toolset_id, version)
            session_id: str | None = None
            try:
                session_id = await self._connect_profile(snapshot.connection)
                discovered = {
                    tool.name: tool
                    for tool in await self.mcp_manager.list_tools(session_id)
                }
                hard_errors, warnings = _detect_schema_drift(snapshot, discovered)
                if hard_errors:
                    raise ToolsetValidationError("; ".join(hard_errors))
            except Exception:
                if session_id:
                    await self._safe_disconnect(session_id)
                raise
            if session_id is None:
                raise ToolsetValidationError("MCP Toolset session did not start.")
            self._version_warnings[key] = warnings
            self._version_sessions[key] = session_id
            return session_id

    async def call_published_tool(
        self,
        *,
        toolset_id: str,
        version: int,
        exposed_name: str,
        arguments: dict[str, Any],
    ) -> RuntimeToolResult:
        snapshot = self.store.get_version(toolset_id, version)
        tool = next(
            (row for row in snapshot.tools if row.exposed_name == exposed_name),
            None,
        )
        if tool is None:
            raise RuntimeToolError(
                exposed_name,
                "Tool is not enabled in the fixed Toolset version.",
                code="toolset_scope_denied",
            )
        merged = {**deepcopy(tool.default_arguments), **dict(arguments)}
        try:
            _validate_arguments(tool, merged)
            session_id = await self.ensure_version_session(toolset_id, version)
            result = await self.mcp_manager.call_tool(
                session_id,
                tool.raw_name,
                merged,
            )
        except RuntimeToolError:
            raise
        except Exception as exc:
            raise RuntimeToolError(
                exposed_name,
                str(exc)[:500],
                code="toolset_call_failed",
            ) from exc
        normalized = _normalize_result(
            result,
            toolset_id=toolset_id,
            version=version,
        )
        warnings = self._version_warnings.get((toolset_id, version), [])
        if warnings:
            normalized.metadata["schema_warnings"] = list(warnings)
        return normalized

    async def _connect_profile(self, profile: Any) -> str:
        profile = self._resolve_installed_project(profile)
        headers: dict[str, str] = {}
        environment: dict[str, str] = {}
        for binding in profile.headers:
            value = self.credentials.resolve(binding.credential_id)
            headers[binding.name] = (
                value
                if binding.name.lower() != "authorization"
                or value.lower().startswith(("bearer ", "basic "))
                else f"Bearer {value}"
            )
        for binding in profile.environment:
            environment[binding.name] = self.credentials.resolve(
                binding.credential_id
            )
        return await self.mcp_manager.connect_profile(
            transport=profile.transport,
            server_command=profile.command,
            url=profile.url,
            headers=headers,
            environment=environment,
            network_policy=profile.network_policy,
            reconnect_attempts=(
                profile.reconnect_attempts if profile.auto_reconnect else 0
            ),
            operation_timeout=profile.timeout_seconds,
            working_directory=profile.working_directory,
        )

    def _resolve_installed_project(
        self,
        profile: MCPConnectionProfile,
    ) -> MCPConnectionProfile:
        resolved = profile.model_copy(deep=True)
        project_id = resolved.installed_project_id.strip()
        if resolved.transport != "stdio" or not project_id:
            return resolved
        if resolved.command:
            return resolved
        if self.installed_project_resolver is None:
            raise ToolsetValidationError(
                "Installed MCP project resolver is unavailable."
            )
        project = self.installed_project_resolver(project_id)
        if not project:
            raise ToolsetValidationError(
                f"Installed MCP project not found: {project_id}"
            )
        command = [
            str(part)
            for part in list(project.get("server_command") or [])
            if isinstance(part, str) and part
        ]
        if not command:
            raise ToolsetValidationError(
                f"Installed MCP project is not runnable: {project_id}"
            )
        resolved.command = command
        return resolved

    async def _safe_disconnect(self, session_id: str) -> None:
        try:
            await self.mcp_manager.disconnect(session_id)
        except Exception:
            pass


class PublishedMCPToolsetProvider:
    provider_name = "published_mcp_toolset"

    def __init__(self, service: ToolsetService) -> None:
        self.service = service

    async def list_tools(
        self,
        resources: list[dict[str, Any]] | None = None,
    ) -> list[RuntimeTool]:
        result: list[RuntimeTool] = []
        for resource in resources or []:
            toolset_id = str(resource.get("toolset_id") or "")
            version = int(resource.get("pinned_version") or 0)
            if not toolset_id or version < 1:
                continue
            snapshot = self.service.store.get_version(toolset_id, version)
            prefix = snapshot.connection.tool_prefix
            for tool in snapshot.tools:
                exposed = tool.exposed_name
                if prefix:
                    exposed = f"{prefix}_{exposed}"
                result.append(
                    RuntimeTool(
                        name=exposed,
                        description=tool.exposed_description,
                        input_schema=deepcopy(tool.input_schema),
                        provider=self.provider_name,
                        metadata={
                            "toolset_id": toolset_id,
                            "toolset_version": version,
                            "toolset_raw_name": tool.raw_name,
                            "toolset_exposed_name": tool.exposed_name,
                        },
                    )
                )
        return result

    async def find_tool(
        self,
        tool_name: str,
        resources: list[dict[str, Any]] | None = None,
    ) -> RuntimeTool | None:
        return next(
            (tool for tool in await self.list_tools(resources) if tool.name == tool_name),
            None,
        )

    async def call_tool(self, call: RuntimeToolCall) -> RuntimeToolResult:
        resources = list(call.metadata.get("toolset_resources") or [])
        matched = await self.find_tool(call.tool_name, resources)
        if matched is None:
            raise RuntimeToolError(
                call.tool_name,
                "Tool is outside the bound Toolset scope.",
                code="toolset_scope_denied",
            )
        metadata = matched.metadata
        return await self.service.call_published_tool(
            toolset_id=str(metadata["toolset_id"]),
            version=int(metadata["toolset_version"]),
            exposed_name=str(metadata["toolset_exposed_name"]),
            arguments=call.arguments,
        )


class DraftMCPToolTestProvider:
    """Scoped provider used only by the trusted Toolset management test action."""

    def __init__(self, service: ToolsetService) -> None:
        self.service = service

    async def call_tool(self, call: RuntimeToolCall) -> RuntimeToolResult:
        if not call.metadata.get("toolset_test"):
            raise RuntimeToolError(
                call.tool_name,
                "Draft Toolset test scope is missing.",
                code="toolset_scope_denied",
            )
        session_id = str(call.metadata.get("toolset_session_id") or "")
        raw_name = str(call.metadata.get("toolset_raw_name") or "")
        toolset_id = str(call.metadata.get("toolset_id") or "")
        if not session_id or not raw_name or not toolset_id:
            raise RuntimeToolError(
                call.tool_name,
                "Draft Toolset test metadata is incomplete.",
                code="toolset_scope_denied",
            )
        try:
            result = await self.service.mcp_manager.call_tool(
                session_id,
                raw_name,
                call.arguments,
            )
        except Exception as exc:
            raise RuntimeToolError(
                call.tool_name,
                str(exc)[:500],
                code="toolset_test_failed",
            ) from exc
        return _normalize_result(result, toolset_id=toolset_id, version=None)


def _normalize_tool(tool: Any) -> ToolDefinition:
    if hasattr(tool, "model_dump"):
        data = tool.model_dump(by_alias=True)
    elif isinstance(tool, dict):
        data = dict(tool)
    else:
        data = vars(tool)
    schema = data.get("inputSchema") or data.get("input_schema") or {}
    return ToolDefinition(
        original_name=str(data.get("name") or ""),
        description=str(data.get("description") or ""),
        input_schema=dict(schema) if isinstance(schema, dict) else {},
        schema_hash=_schema_hash(schema if isinstance(schema, dict) else {}),
    )


def _validate_arguments(tool: ToolDefinition, arguments: dict[str, Any]) -> None:
    try:
        Draft202012Validator(tool.input_schema or {}).validate(arguments)
    except Exception as exc:
        raise ToolsetValidationError(
            f"Arguments do not match {tool.exposed_name} schema: {str(exc)[:300]}"
        ) from exc


def _detect_schema_drift(
    snapshot: ToolsetVersion,
    discovered: dict[str, Any],
) -> tuple[list[str], list[str]]:
    hard_errors: list[str] = []
    warnings: list[str] = []
    for expected in snapshot.tools:
        current_raw = discovered.get(expected.raw_name)
        if current_raw is None:
            hard_errors.append(f"Published tool disappeared: {expected.raw_name}")
            continue
        current = _normalize_tool(current_raw)
        old_required = set(expected.input_schema.get("required") or [])
        new_required = set(current.input_schema.get("required") or [])
        added_required = sorted(new_required - old_required)
        if added_required:
            hard_errors.append(
                f"{expected.raw_name} added required parameters: "
                f"{', '.join(added_required)}"
            )
        old_properties = expected.input_schema.get("properties") or {}
        new_properties = current.input_schema.get("properties") or {}
        if isinstance(old_properties, dict) and isinstance(new_properties, dict):
            changed_types = sorted(
                name
                for name, old_schema in old_properties.items()
                if name in new_properties
                and isinstance(old_schema, dict)
                and isinstance(new_properties[name], dict)
                and old_schema.get("type")
                and new_properties[name].get("type")
                and old_schema.get("type") != new_properties[name].get("type")
            )
            if changed_types:
                hard_errors.append(
                    f"{expected.raw_name} changed parameter types: "
                    f"{', '.join(changed_types)}"
                )
        if (
            not added_required
            and not any(
                message.startswith(
                    f"{expected.raw_name} changed parameter types:"
                )
                for message in hard_errors
            )
            and current.schema_hash != expected.schema_hash
        ):
            warnings.append(f"{expected.raw_name} schema changed compatibly.")
    return hard_errors, warnings


def _normalize_result(
    result: Any,
    *,
    toolset_id: str,
    version: int | None,
) -> RuntimeToolResult:
    content_items = list(getattr(result, "content", []) or [])
    content: list[dict[str, Any]] = []
    text_parts: list[str] = []
    for item in content_items:
        if hasattr(item, "model_dump"):
            value = dict(item.model_dump())
        elif isinstance(item, dict):
            value = dict(item)
        else:
            value = {"type": "unknown", "raw": str(item)}
        content.append(value)
        if value.get("type") == "text" and isinstance(value.get("text"), str):
            text_parts.append(value["text"])
    output = "\n\n".join(text_parts)
    if len(output) > 65536:
        output = output[:65536] + "\n...[truncated]"
    return RuntimeToolResult(
        output=output,
        content=content[:50],
        metadata={
            "toolset_id": toolset_id,
            "toolset_version": version,
            "output_length": len(output),
        },
        is_error=bool(
            getattr(result, "isError", False)
            or getattr(result, "is_error", False)
        ),
    )
