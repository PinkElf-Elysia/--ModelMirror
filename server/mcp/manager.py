"""Async MCP stdio client session manager for ModelMirror.

The official MCP stdio transport uses AnyIO cancel scopes that must be entered
and exited in the same task. FastAPI requests, however, arrive in different
tasks. To keep the integration safe, each MCP session is owned by a dedicated
worker task. Public manager methods communicate with that task through an
``asyncio.Queue``; all SDK calls and cleanup happen inside the owner task.
"""

from __future__ import annotations

import asyncio
import os
import time
import uuid
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable, Literal

from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.types import CallToolResult, Tool


class MCPClientError(RuntimeError):
    """Base error for MCP client manager failures."""


class MCPSessionNotFoundError(MCPClientError):
    """Raised when a session id is unknown or has already been disconnected."""


FORBIDDEN_COMMAND_TOKENS = (";", "&&", "||", "|", ">", "<", "`", "$(", "\n", "\r")
SessionOperation = Literal["list_tools", "call_tool", "disconnect"]


def validate_server_command(server_command: list[str]) -> None:
    """Validate that a command is a shell-free argv list."""

    if not server_command:
        raise ValueError("server_command 不能为空。")
    if not all(isinstance(part, str) and part.strip() for part in server_command):
        raise ValueError("server_command 必须是非空字符串数组。")

    for part in server_command:
        if any(token in part for token in FORBIDDEN_COMMAND_TOKENS):
            raise ValueError("server_command 包含不允许的 shell 特殊字符。")


@dataclass(slots=True)
class SessionCommand:
    """A queued command to execute inside a session owner task."""

    operation: SessionOperation
    future: asyncio.Future[Any]
    tool_name: str | None = None
    arguments: dict[str, Any] | None = None


@dataclass(slots=True)
class ManagedMCPSession:
    """A live MCP stdio session controlled by an owner task."""

    session_id: str
    command: list[str]
    created_at: float
    created_monotonic_at: float
    last_used_at: float
    queue: asyncio.Queue[SessionCommand] = field(default_factory=asyncio.Queue)
    task: asyncio.Task[None] | None = None
    tools_count: int = 0
    status: str = "starting"
    restart_count: int = 0


class MCPClientManager:
    """Manage multiple MCP stdio server sessions."""

    def __init__(
        self,
        *,
        sandbox_root: Path | None = None,
        operation_timeout: float = 30,
        idle_timeout_seconds: float = 30 * 60,
        cleanup_interval_seconds: float = 5 * 60,
    ) -> None:
        self.sandbox_root = (
            sandbox_root
            if sandbox_root is not None
            else Path(__file__).resolve().parent / "sandboxes"
        )
        self.operation_timeout = operation_timeout
        self.idle_timeout_seconds = idle_timeout_seconds
        self.cleanup_interval_seconds = cleanup_interval_seconds
        self._sessions: dict[str, ManagedMCPSession] = {}
        self._lock = asyncio.Lock()
        self._cleanup_task: asyncio.Task[None] | None = None
        self._cleanup_callback: Callable[[list[str]], Awaitable[None]] | None = None
        self.sandbox_root.mkdir(parents=True, exist_ok=True)

    async def connect(self, server_command: list[str]) -> str:
        """Start an MCP server owner task and return a session id."""

        validate_server_command(server_command)
        managed = self._new_managed_session(server_command)
        ready: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        managed.task = asyncio.create_task(self._session_worker(managed, ready))
        try:
            await asyncio.wait_for(ready, timeout=self.operation_timeout)
        except Exception:
            if managed.task:
                managed.task.cancel()
                await asyncio.gather(managed.task, return_exceptions=True)
            raise

        async with self._lock:
            self._sessions[managed.session_id] = managed
        return managed.session_id

    async def list_tools(self, session_id: str) -> list[Tool]:
        """Return tools exposed by the MCP server for ``session_id``."""

        managed = await self._get_session(session_id)
        try:
            tools = await self._send_command(managed, "list_tools")
        except Exception as exc:
            managed = await self._restart_once(managed, exc)
            tools = await self._send_command(managed, "list_tools")
        managed.tools_count = len(tools)
        return tools

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
        try:
            return await self._send_command(
                managed,
                "call_tool",
                tool_name=tool_name,
                arguments=arguments or {},
            )
        except Exception as exc:
            managed = await self._restart_once(managed, exc)
            return await self._send_command(
                managed,
                "call_tool",
                tool_name=tool_name,
                arguments=arguments or {},
            )

    async def disconnect(self, session_id: str) -> None:
        """Disconnect and clean up a session if it exists."""

        async with self._lock:
            managed = self._sessions.pop(session_id, None)
        if managed is None:
            raise MCPSessionNotFoundError(f"MCP session not found: {session_id}")
        await self._stop_session(managed)

    async def get_sessions_summary(self) -> list[dict[str, Any]]:
        """Return serializable metadata for active sessions."""

        now_mono = time.monotonic()
        async with self._lock:
            sessions = list(self._sessions.values())

        return [
            {
                "session_id": managed.session_id,
                "server_command": list(managed.command),
                "status": managed.status,
                "created_at": managed.created_at,
                "uptime_seconds": max(0, now_mono - managed.created_monotonic_at),
                "idle_seconds": max(0, now_mono - managed.last_used_at),
                "tools_count": managed.tools_count,
            }
            for managed in sessions
        ]

    async def cleanup_idle_sessions(self) -> list[str]:
        """Disconnect idle sessions and return cleaned session ids."""

        now = time.monotonic()
        expired: list[ManagedMCPSession] = []
        async with self._lock:
            for session_id, managed in list(self._sessions.items()):
                if now - managed.last_used_at > self.idle_timeout_seconds:
                    expired.append(self._sessions.pop(session_id))

        cleaned_ids: list[str] = []
        for managed in expired:
            cleaned_ids.append(managed.session_id)
            await self._stop_session(managed)
        return cleaned_ids

    def start_ttl_cleanup(
        self,
        *,
        on_cleanup: Callable[[list[str]], Awaitable[None]] | None = None,
        interval_seconds: float | None = None,
    ) -> None:
        """Start a non-blocking TTL cleanup loop if it is not running."""

        if self._cleanup_task and not self._cleanup_task.done():
            return
        self._cleanup_callback = on_cleanup
        interval = interval_seconds or self.cleanup_interval_seconds
        self._cleanup_task = asyncio.create_task(self._cleanup_loop(interval))

    async def stop_ttl_cleanup(self) -> None:
        """Stop the TTL cleanup loop and wait for cancellation."""

        task = self._cleanup_task
        self._cleanup_task = None
        if task is None:
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    async def close_all(self) -> None:
        """Disconnect every managed session."""

        async with self._lock:
            sessions = list(self._sessions.values())
            self._sessions.clear()
        for managed in sessions:
            await self._stop_session(managed)

    def _new_managed_session(
        self,
        server_command: list[str],
        *,
        session_id: str | None = None,
        restart_count: int = 0,
    ) -> ManagedMCPSession:
        now_epoch = time.time()
        now_mono = time.monotonic()
        return ManagedMCPSession(
            session_id=session_id or uuid.uuid4().hex,
            command=list(server_command),
            created_at=now_epoch,
            created_monotonic_at=now_mono,
            last_used_at=now_mono,
            restart_count=restart_count,
        )

    async def _session_worker(
        self,
        managed: ManagedMCPSession,
        ready: asyncio.Future[None],
    ) -> None:
        try:
            command, *args = managed.command
            params = StdioServerParameters(
                command=command,
                args=args,
                env=self._child_env(),
                cwd=str(self.sandbox_root),
            )
            async with AsyncExitStack() as exit_stack:
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
                managed.status = "connected"
                if not ready.done():
                    ready.set_result(None)

                while True:
                    command_item = await managed.queue.get()
                    if command_item.operation == "disconnect":
                        managed.status = "disconnected"
                        if not command_item.future.done():
                            command_item.future.set_result(None)
                        break

                    try:
                        managed.last_used_at = time.monotonic()
                        if command_item.operation == "list_tools":
                            result = await asyncio.wait_for(
                                client_session.list_tools(),
                                timeout=self.operation_timeout,
                            )
                            tools = list(result.tools)
                            managed.tools_count = len(tools)
                            command_item.future.set_result(tools)
                        elif command_item.operation == "call_tool":
                            result = await asyncio.wait_for(
                                client_session.call_tool(
                                    command_item.tool_name or "",
                                    command_item.arguments or {},
                                ),
                                timeout=self.operation_timeout,
                            )
                            command_item.future.set_result(result)
                    except Exception as exc:
                        if not command_item.future.done():
                            command_item.future.set_exception(exc)
        except Exception as exc:
            managed.status = "error"
            if not ready.done():
                ready.set_exception(exc)
            while not managed.queue.empty():
                command_item = managed.queue.get_nowait()
                if not command_item.future.done():
                    command_item.future.set_exception(exc)

    async def _send_command(
        self,
        managed: ManagedMCPSession,
        operation: SessionOperation,
        *,
        tool_name: str | None = None,
        arguments: dict[str, Any] | None = None,
    ) -> Any:
        if managed.task is None or managed.task.done():
            raise MCPClientError("MCP session is not running.")
        future: asyncio.Future[Any] = asyncio.get_running_loop().create_future()
        await managed.queue.put(
            SessionCommand(
                operation=operation,
                future=future,
                tool_name=tool_name,
                arguments=arguments,
            )
        )
        return await asyncio.wait_for(future, timeout=self.operation_timeout + 5)

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
        await self._stop_session(managed, raise_on_error=False)
        restarted = self._new_managed_session(
            command,
            session_id=old_session_id,
            restart_count=managed.restart_count + 1,
        )
        ready: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        restarted.task = asyncio.create_task(self._session_worker(restarted, ready))
        await asyncio.wait_for(ready, timeout=self.operation_timeout)
        async with self._lock:
            self._sessions[old_session_id] = restarted
        return restarted

    async def _get_session(self, session_id: str) -> ManagedMCPSession:
        async with self._lock:
            managed = self._sessions.get(session_id)
        if managed is None:
            raise MCPSessionNotFoundError(f"MCP session not found: {session_id}")
        return managed

    async def _stop_session(
        self,
        managed: ManagedMCPSession,
        *,
        raise_on_error: bool = True,
    ) -> None:
        try:
            if managed.task and not managed.task.done():
                try:
                    await self._send_command(managed, "disconnect")
                except Exception:
                    managed.task.cancel()
                await asyncio.gather(managed.task, return_exceptions=True)
        except Exception as exc:
            if raise_on_error:
                raise MCPClientError(f"关闭 MCP session 失败：{exc}") from exc

    async def _cleanup_loop(self, interval_seconds: float) -> None:
        while True:
            await asyncio.sleep(interval_seconds)
            cleaned_ids = await self.cleanup_idle_sessions()
            if cleaned_ids and self._cleanup_callback is not None:
                try:
                    await self._cleanup_callback(cleaned_ids)
                except Exception:
                    # Keep the cleanup loop alive even if a downstream registry
                    # cleanup fails. The next sweep can retry stale resources.
                    pass

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
