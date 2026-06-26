from __future__ import annotations

import pytest

from server.main import (
    ChatMessage,
    parse_upstream_error,
    sse_delta_text,
    stream_chat_text,
)
from server.xpert_runtime import (
    MiddlewareContext,
    ModelCallRequest,
    ModelCallResponse,
    RuntimeEventStore,
    create_default_runtime,
    event_recorder,
)


@pytest.mark.asyncio
async def test_middleware_injects_system_prompt_in_chat() -> None:
    pipeline, context = create_default_runtime()
    context.metadata["system_prompt"] = "你是助手"

    request = ModelCallRequest(
        model_id="mock-model",
        messages=[{"role": "user", "content": "你好"}],
    )

    prepared = await pipeline.before_model(request, context)

    assert prepared.messages[0] == {"role": "system", "content": "你是助手"}
    assert prepared.messages[1] == {"role": "user", "content": "你好"}


@pytest.mark.asyncio
async def test_chat_events_recorded_in_store() -> None:
    store = RuntimeEventStore()
    pipeline, context = create_default_runtime(store=store, middlewares=[event_recorder])
    context.task_id = "chat-task-1"
    context.metadata = {"model_id": "mock-model", "message_count": 1}

    await pipeline.before_agent(
        {"model_id": "mock-model", "messages": [{"role": "user", "content": "hi"}]},
        context,
    )
    await pipeline.before_model(
        ModelCallRequest(
            model_id="mock-model",
            messages=[{"role": "user", "content": "hi"}],
        ),
        context,
    )
    await pipeline.after_model(
        ModelCallResponse(text="hello", metadata={"model_id": "mock-model"}),
        context,
    )
    await pipeline.after_agent({"status": "completed"}, context)

    events = await store.list_events("chat-task-1")

    assert [event.type for event in events] == [
        "chat.started",
        "model.call.started",
        "model.call.finished",
        "chat.finished",
    ]


@pytest.mark.asyncio
async def test_sse_text_stream_passthrough(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeResponse:
        status_code = 200

        async def aiter_text(self):
            yield 'data: {"choices":[{"delta":{"content":"hello "}}]}\n\n'
            yield 'data: {"choices":[{"delta":{"content":"world"}}]}\n\n'
            yield "data: [DONE]\n\n"

        async def aclose(self) -> None:
            return None

    class FakeClient:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        def build_request(self, method, url, headers, json):
            return {"method": method, "url": url, "headers": headers, "json": json}

        async def send(self, request, stream):
            assert stream is True
            return FakeResponse()

    import server.main as main_module

    monkeypatch.setattr(main_module, "get_llm_gateway_config", lambda: ("http://mock", "key"))
    monkeypatch.setattr(main_module.httpx, "AsyncClient", FakeClient)

    chunks = [
        chunk
        async for chunk in stream_chat_text(
            "mock-model",
            [ChatMessage(role="user", content="hi")],
        )
    ]

    assert "".join(chunks) == "hello world"


@pytest.mark.asyncio
async def test_image_markdown_output_preserved() -> None:
    pipeline, context = create_default_runtime(middlewares=[event_recorder])
    response = ModelCallResponse(
        text="结果：\n![图片](https://example.com/img.png)\n",
        metadata={"model_id": "image-model"},
    )

    processed = await pipeline.after_model(response, context)

    assert processed.text == response.text
    assert "![图片](https://example.com/img.png)" in processed.text


def test_sse_image_url_is_converted_to_markdown() -> None:
    event = (
        'data: {"choices":[{"delta":{"content":[{"type":"image_url",'
        '"image_url":{"url":"https://example.com/cat.png"}}]}}]}\n\n'
    )

    assert sse_delta_text(event) == ["\n![图片](https://example.com/cat.png)\n"]


def test_user_not_found_error_is_mapped_to_actionable_message() -> None:
    message, data = parse_upstream_error(
        401,
        b'{"error":{"message":"User not found."}}',
    )

    assert data is not None
    assert "User not found" not in message
    assert "newAPI" in message
    assert "OPENROUTER_API_KEY" in message


def test_newapi_user_error_can_fallback_to_openrouter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import server.main as main_module

    monkeypatch.setattr(main_module, "OPENROUTER_API_KEY", "sk-test")

    assert (
        main_module.should_fallback_gateway_to_openrouter(
            401,
            "本地 newAPI 未找到对应用户或令牌无效。",
            {"error": {"message": "User not found."}},
            "http://new-api:3000/v1/chat/completions",
        )
        is True
    )
    assert (
        main_module.should_fallback_gateway_to_openrouter(
            401,
            "本地 newAPI 未找到对应用户或令牌无效。",
            {"error": {"message": "User not found."}},
            main_module.CHAT_COMPLETIONS_URL,
        )
        is False
    )
