"""In-memory MCP tool registry.

The registry aggregates tools exposed by all active MCP sessions. It keeps the
raw per-session mapping and exposes a deduplicated global list where the first
tool name wins, matching the current product requirement.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any

from mcp.types import Tool


@dataclass(slots=True)
class RegisteredTool:
    """Serializable metadata for one MCP tool."""

    name: str
    description: str | None
    input_schema: dict[str, Any]
    server_id: str
    session_id: str
    registered_at: float


class ToolRegistry:
    """Thread-safe in-memory registry for active MCP tools."""

    def __init__(self) -> None:
        self._tools_by_session: dict[str, list[RegisteredTool]] = {}
        self._lock = asyncio.Lock()

    async def register_session_tools(
        self,
        *,
        session_id: str,
        server_id: str,
        tools: list[Tool],
    ) -> None:
        """Replace the tools registered for one session."""

        registered_at = time.time()
        records = [
            RegisteredTool(
                name=tool.name,
                description=tool.description,
                input_schema=tool.inputSchema,
                server_id=server_id,
                session_id=session_id,
                registered_at=registered_at,
            )
            for tool in tools
        ]
        async with self._lock:
            self._tools_by_session[session_id] = records

    async def unregister_session(self, session_id: str) -> None:
        """Remove all tools belonging to a session."""

        async with self._lock:
            self._tools_by_session.pop(session_id, None)

    async def unregister_sessions(self, session_ids: list[str]) -> None:
        """Remove all tools belonging to a list of sessions."""

        async with self._lock:
            for session_id in session_ids:
                self._tools_by_session.pop(session_id, None)

    async def list_tools(self) -> list[dict[str, Any]]:
        """Return the deduplicated global tool list.

        If multiple sessions expose the same tool name, the first registered
        tool is kept and later duplicates are ignored.
        """

        async with self._lock:
            sessions = list(self._tools_by_session.values())

        seen: set[str] = set()
        aggregated: list[dict[str, Any]] = []
        for records in sessions:
            for record in records:
                if record.name in seen:
                    continue
                seen.add(record.name)
                aggregated.append(
                    {
                        "name": record.name,
                        "description": record.description,
                        "input_schema": record.input_schema,
                        "server_id": record.server_id,
                        "session_id": record.session_id,
                        "registered_at": record.registered_at,
                    }
                )
        return aggregated

    async def clear(self) -> None:
        """Clear all registered tools."""

        async with self._lock:
            self._tools_by_session.clear()
