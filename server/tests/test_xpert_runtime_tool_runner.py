from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from server.xpert_runtime import (
    AgentMiddleware,
    CapabilityRegistry,
    MiddlewareContext,
    MiddlewarePipeline,
    RuntimeEventStore,
    RuntimeToolCall,
    RuntimeToolResult,
    ToolCallResponse,
    event_recorder,
    run_tool_with_runtime,
)


@pytest.mark.asyncio
async def test_run_tool_with_registered_capability() -> None:
    provider = MagicMock()
    provider.call_tool = AsyncMock(
        return_value=RuntimeToolResult(
            output="hello",
            content=[{"type": "text", "text": "hello"}],
            metadata={"content_types": ["text"]},
            is_error=False,
        )
    )
    registry = CapabilityRegistry()
    registry.register("mcp_tools", provider)

    result = await run_tool_with_runtime(
        RuntimeToolCall(tool_name="echo", arguments={"msg": "hi"}),
        registry,
        MiddlewarePipeline([]),
        MiddlewareContext(),
    )

    assert result.output == "hello"
    assert result.is_error is False
    provider.call_tool.assert_awaited_once()
    called = provider.call_tool.await_args.args[0]
    assert called.tool_name == "echo"
    assert called.arguments == {"msg": "hi"}


@pytest.mark.asyncio
async def test_wrap_tool_call_middleware_is_invoked() -> None:
    provider = MagicMock()
    provider.call_tool = AsyncMock(
        return_value=RuntimeToolResult(
            output="original",
            content=[{"type": "text", "text": "original"}],
            metadata={"content_types": ["text"]},
        )
    )
    calls = {"count": 0}

    async def wrap_tool_call(request, handler, context):
        calls["count"] += 1
        response = await handler(request)
        return response.with_updates(output=f"[wrapped] {response.output}")

    registry = CapabilityRegistry()
    registry.register("mcp_tools", provider)

    result = await run_tool_with_runtime(
        RuntimeToolCall(tool_name="echo", arguments={}),
        registry,
        MiddlewarePipeline(
            [AgentMiddleware(name="wrap-test", wrap_tool_call=wrap_tool_call)]
        ),
        MiddlewareContext(),
    )

    assert result.output == "[wrapped] original"
    assert calls["count"] == 1
    provider.call_tool.assert_awaited_once()


@pytest.mark.asyncio
async def test_middleware_error_falls_back_to_direct_call() -> None:
    provider = MagicMock()
    provider.call_tool = AsyncMock(
        return_value=RuntimeToolResult(
            output="fallback result",
            content=[{"type": "text", "text": "fallback result"}],
            metadata={"content_types": ["text"]},
        )
    )

    async def broken_wrap_tool_call(request, handler, context) -> ToolCallResponse:
        raise RuntimeError("middleware broken")

    registry = CapabilityRegistry()
    registry.register("mcp_tools", provider)

    result = await run_tool_with_runtime(
        RuntimeToolCall(tool_name="echo", arguments={}),
        registry,
        MiddlewarePipeline(
            [AgentMiddleware(name="broken", wrap_tool_call=broken_wrap_tool_call)]
        ),
        MiddlewareContext(),
    )

    assert result.output == "fallback result"
    provider.call_tool.assert_awaited_once()


@pytest.mark.asyncio
async def test_tool_call_events_are_recorded() -> None:
    provider = MagicMock()
    provider.call_tool = AsyncMock(
        return_value=RuntimeToolResult(
            output="event test",
            content=[{"type": "text", "text": "event test"}],
            metadata={"content_types": ["text"]},
        )
    )
    registry = CapabilityRegistry()
    registry.register("mcp_tools", provider)
    store = RuntimeEventStore()
    task = await store.create_task("tool_test")

    await run_tool_with_runtime(
        RuntimeToolCall(tool_name="echo", arguments={"msg": "hi"}),
        registry,
        MiddlewarePipeline([event_recorder]),
        MiddlewareContext(task_id=task.id, store=store),
    )

    events = await store.list_events(task.id)
    event_types = [event.type for event in events]
    assert "tool.call.started" in event_types
    assert "tool.call.finished" in event_types

    started = next(event for event in events if event.type == "tool.call.started")
    finished = next(event for event in events if event.type == "tool.call.finished")
    assert started.payload["tool_name"] == "echo"
    assert started.payload["arguments_count"] == 1
    assert finished.payload["output_length"] == len("event test")
