"""Async MCP stdio client session manager for ModelMirror.

The manager owns MCP server subprocess lifecycles through the official
``mcp`` Python SDK. It intentionally exposes a small API that can be reused by
FastAPI routes, smoke scripts, and future workflow tooling.
"""

from __future__ import annotations

import asyncio
import os
import time
import uuid
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.types import CallToolResult, Tool


class MCPClientError(RuntimeError):
    """Base error for MCP client manager failures."""


class MCPSessionNotFoundError(MCPClientError):
    """Raised when a session id is unknown or has already been disconnected."""


FORBIDDEN_COMMAND_TOKENS = (";", "&&", "||", "|", ">", "<", "`", "$(", "\n", "\r")


def validate_server_command(server_command: list[str]) -> None:
    """Validate that a command is a shell-free argv list.

    The command is later passed to the MCP SDK as argv, not to a shell. This
    check prevents obviously unsafe shell metacharacters from being accepted at
    the API boundary.
    """

    if not server_command:
        raise ValueError("server_command 不能为空。")
    if not all(isinstance(part, str) and part.strip() for part in server_command):
        raise ValueError("server_command 必须是非空字符串数组。")

    for part in server_command:
        if any(token in part for token in FORBIDDEN_COMMAND_TOKENS):
            raise ValueError("server_command 包含不允许的 shell 特殊字符。")


@dataclass(slots=True)
class ManagedMCPSession:
    """A live MCP stdio session and its lifecycle resources."""

    session_id: str
    command: list[str]
    session: ClientSession
    exit_stack: AsyncExitStack
    created_at: float
    last_used_at: float
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    restart_count: int = 0


class MCPClientManager:
    """Manage MCP stdio server sessions.

    Parameters
    ----------
    sandbox_root:
        Directory used as the working directory for every MCP server process.
    operation_timeout:
        Max seconds for initialize/list/call operations.
    idle_timeout_seconds:
        Sessions unused for this many seconds are eligible for cleanup.
    """

    def __init__(
        self,
        *,
        sandbox_root: Path | None = None,
        operation_timeout: float = 30,
        idle_timeout_seconds: float = 15 * 60,
    ) -> None:
        self.sandbox_root = (
            sandbox_root
            if sandbox_root is not None
            else Path(__file__).resolve().parent / "sandboxes"
        )
        self.operation_timeout = operation_timeout
        self.idle_timeout_seconds = idle_timeout_seconds
        self._sessions: dict[str, ManagedMCPSession] = {}
        self._lock = asyncio.Lock()
        self.sandbox_root.mkdir(parents=True, exist_ok=True)

    async def connect(self, server_command: list[str]) -> str:
        """Start an MCP server process and return a new session id."""

        validate_server_command(server_command)
        managed = await self._open_session(server_command)
        async with self._lock:
            self._sessions[managed.session_id] = managed
        return managed.session_id

    async def list_tools(self, session_id: str) -> list[Tool]:
        """Return tools exposed by the MCP server for ``session_id``."""

        managed = await self._get_session(session_id)
        async with managed.lock:
            managed.last_used_at = time.monotonic()
            try:
                result = await asyncio.wait_for(
                    managed.session.list_tools(),
                    timeout=self.operation_timeout,
                )
            except Exception as exc:
                managed = await self._restart_once(managed, exc)
                result = await asyncio.wait_for(
                    managed.session.list_tools(),
                    timeout=self.operation_timeout,
                )
            return list(result.tools)

    async def call_tool(
        self,
        session_id: str,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
    ) -> CallToolResult:
        """Call a named MCP tool with JSON-like arguments."""

        if not tool_name.strip():
            raise ValueError("tool_name 不能为空。")

        managed = await self._get_session(session_id)
        async with managed.lock:
            managed.last_used_at = time.monotonic()
            try:
                return await asyncio.wait_for(
                    managed.session.call_tool(tool_name, arguments or {}),
                    timeout=self.operation_timeout,
                )
            except Exception as exc:
                managed = await self._restart_once(managed, exc)
                return await asyncio.wait_for(
                    managed.session.call_tool(tool_name, arguments or {}),
                    timeout=self.operation_timeout,
                )

    async def disconnect(self, session_id: str) -> None:
        """Disconnect and clean up a session if it exists."""

        async with self._lock:
            managed = self._sessions.pop(session_id, None)
        if managed is None:
            raise MCPSessionNotFoundError(f"MCP session not found: {session_id}")
        await self._close_managed_session(managed)

    async def cleanup_idle_sessions(self) -> int:
        """Disconnect idle sessions and return the number cleaned up."""

        now = time.monotonic()
        expired: list[ManagedMCPSession] = []
        async with self._lock:
            for session_id, managed in list(self._sessions.items()):
                if now - managed.last_used_at > self.idle_timeout_seconds:
                    expired.append(self._sessions.pop(session_id))

        for managed in expired:
            await self._close_managed_session(managed)
        return len(expired)

    async def close_all(self) -> None:
        """Disconnect every managed session."""

        async with self._lock:
            sessions = list(self._sessions.values())
            self._sessions.clear()
        for managed in sessions:
            await self._close_managed_session(managed)

    async def _open_session(
        self,
        server_command: list[str],
        *,
        session_id: str | None = None,
        restart_count: int = 0,
    ) -> ManagedMCPSession:
        command, *args = server_command
        exit_stack = AsyncExitStack()
        env = self._child_env()
        params = StdioServerParameters(
            command=command,
            args=args,
            env=env,
            cwd=str(self.sandbox_root),
        )

        try:
            read_stream, write_stream = await exit_stack.enter_async_context(
                stdio_client(params)
            )
            client_session = await exit_stack.enter_async_context(
                ClientSession(read_stream, write_stream)
            )
            await asyncio.wait_for(
                client_session.initialize(),
                timeout=self.operation_timeout,
            )
        except Exception:
            await exit_stack.aclose()
            raise

        now = time.monotonic()
        return ManagedMCPSession(
            session_id=session_id or uuid.uuid4().hex,
            command=list(server_command),
            session=client_session,
            exit_stack=exit_stack,
            created_at=now,
            last_used_at=now,
            restart_count=restart_count,
        )

    async def _restart_once(
        self,
        managed: ManagedMCPSession,
        original_error: Exception,
    ) -> ManagedMCPSession:
        if managed.restart_count >= 1:
            raise MCPClientError(
                f"MCP session 已重启过一次，仍然失败：{original_error}"
            ) from original_error

        old_session_id = managed.session_id
        command = list(managed.command)
        await self._close_managed_session(managed)
        restarted = await self._open_session(
            command,
            session_id=old_session_id,
            restart_count=managed.restart_count + 1,
        )
        async with self._lock:
            self._sessions[old_session_id] = restarted
        return restarted

    async def _get_session(self, session_id: str) -> ManagedMCPSession:
        async with self._lock:
            managed = self._sessions.get(session_id)
        if managed is None:
            raise MCPSessionNotFoundError(f"MCP session not found: {session_id}")
        return managed

    async def _close_managed_session(self, managed: ManagedMCPSession) -> None:
        try:
            await managed.exit_stack.aclose()
        except Exception as exc:
            raise MCPClientError(f"关闭 MCP session 失败：{exc}") from exc

    def _child_env(self) -> dict[str, str]:
        allowed_keys = {
            "PATH",
            "SystemRoot",
            "COMSPEC",
            "PATHEXT",
            "TEMP",
            "TMP",
            "APPDATA",
            "LOCALAPPDATA",
            "USERPROFILE",
            "HOME",
            "NODE_PATH",
            "NPM_CONFIG_PREFIX",
        }
        env = {key: value for key, value in os.environ.items() if key in allowed_keys}
        env.setdefault("NO_COLOR", "1")
        return env
