from __future__ import annotations

import json
from typing import Any

from .capabilities import CapabilityRegistry
from .toolset import RuntimeTool, RuntimeToolCall, RuntimeToolError, RuntimeToolResult


class MemoryToolsetProvider:
    """Runtime tools backed by an injected Xpert context store."""

    def __init__(self, context_store: Any) -> None:
        self.context_store = context_store

    async def list_tools(self) -> list[RuntimeTool]:
        return [
            RuntimeTool(
                name="memory_search",
                description="Search active Xpert or conversation memories.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "scope": {
                            "type": "string",
                            "enum": ["conversation", "xpert", "both"],
                        },
                        "limit": {"type": "integer", "minimum": 1, "maximum": 10},
                    },
                    "required": ["query"],
                },
                provider="memory",
            ),
            RuntimeTool(
                name="memory_get",
                description="Read one active memory by its stable ID.",
                input_schema={
                    "type": "object",
                    "properties": {"memory_id": {"type": "string"}},
                    "required": ["memory_id"],
                },
                provider="memory",
            ),
            RuntimeTool(
                name="memory_propose_write",
                description="Create a memory candidate that requires human approval.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "content": {"type": "string"},
                        "scope": {
                            "type": "string",
                            "enum": ["conversation", "xpert"],
                        },
                        "tags": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["content", "scope"],
                },
                provider="memory",
            ),
        ]

    async def find_tool(self, tool_name: str) -> RuntimeTool | None:
        return next((tool for tool in await self.list_tools() if tool.name == tool_name), None)

    async def call_tool(self, call: RuntimeToolCall) -> RuntimeToolResult:
        xpert_id = str(call.metadata.get("xpert_id") or "").strip()
        conversation_id = str(call.metadata.get("conversation_id") or "").strip() or None
        if not xpert_id:
            raise RuntimeToolError(
                call.tool_name,
                "Memory tools require an Xpert runtime context.",
                code="memory_context_missing",
            )
        try:
            if call.tool_name == "memory_search":
                query = str(call.arguments.get("query") or "").strip()
                scope = str(call.arguments.get("scope") or "both").strip()
                limit = max(1, min(int(call.arguments.get("limit") or 5), 10))
                records = self.context_store.search_memories(
                    xpert_id,
                    query,
                    scope=scope,
                    conversation_id=conversation_id,
                    limit=limit,
                )
                output = json.dumps(
                    [
                        {
                            "memory_id": item.memory_id,
                            "scope": item.scope,
                            "content": item.content,
                            "tags": item.tags,
                        }
                        for item in records
                    ],
                    ensure_ascii=False,
                )
                return RuntimeToolResult(
                    output=output,
                    metadata={"content_types": ["text"], "memory_count": len(records)},
                )
            if call.tool_name == "memory_get":
                memory_id = str(call.arguments.get("memory_id") or "").strip()
                record = self.context_store.get_memory(xpert_id, memory_id)
                if record.status != "active":
                    raise ValueError("Memory is archived.")
                return RuntimeToolResult(
                    output=json.dumps(
                        {
                            "memory_id": record.memory_id,
                            "scope": record.scope,
                            "content": record.content,
                            "tags": record.tags,
                        },
                        ensure_ascii=False,
                    ),
                    metadata={"content_types": ["text"]},
                )
            if call.tool_name == "memory_propose_write":
                content = str(call.arguments.get("content") or "").strip()
                scope = str(call.arguments.get("scope") or "xpert").strip()
                tags_raw = call.arguments.get("tags")
                tags = [str(item) for item in tags_raw] if isinstance(tags_raw, list) else []
                candidate = self.context_store.create_candidate(
                    xpert_id,
                    content=content,
                    scope=scope,
                    conversation_id=conversation_id,
                    tags=tags,
                    source_run_id=str(call.metadata.get("run_id") or "") or None,
                )
                return RuntimeToolResult(
                    output=json.dumps(
                        {
                            "candidate_id": candidate.candidate_id,
                            "status": candidate.status,
                        },
                        ensure_ascii=False,
                    ),
                    metadata={
                        "content_types": ["text"],
                        "candidate_id": candidate.candidate_id,
                    },
                )
        except RuntimeToolError:
            raise
        except Exception as exc:
            raise RuntimeToolError(
                call.tool_name,
                str(exc),
                code="memory_tool_error",
            ) from exc
        raise RuntimeToolError(call.tool_name, "Memory tool not found.", code="tool_not_found")


def register_memory_toolset_capability(
    capability_registry: CapabilityRegistry,
    provider: MemoryToolsetProvider,
) -> None:
    capability_registry.register(
        "memory_tools",
        provider,
        description="Persistent Xpert conversation and long-term memory tools.",
        metadata={"provider": "memory"},
    )
