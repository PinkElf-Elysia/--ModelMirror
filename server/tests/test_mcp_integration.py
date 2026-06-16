from __future__ import annotations

import sys
from pathlib import Path

import httpx
import pytest
import pytest_asyncio

from server.main import app, mcp_connect_windows, mcp_manager


MOCK_SERVER = Path(__file__).resolve().parent / "mock_mcp_server.py"


@pytest_asyncio.fixture(autouse=True)
async def cleanup_sessions():
    mcp_connect_windows.clear()
    yield
    mcp_connect_windows.clear()
    await mcp_manager.close_all()


@pytest_asyncio.fixture
async def client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as async_client:
        yield async_client


@pytest.mark.asyncio
async def test_connect_list_call_and_disconnect(client: httpx.AsyncClient) -> None:
    connect_response = await client.post(
        "/api/mcp/connect",
        json={"server_command": [sys.executable, str(MOCK_SERVER)]},
    )
    assert connect_response.status_code == 200, connect_response.text
    session_id = connect_response.json()["session_id"]
    assert connect_response.json()["tools_count"] >= 1

    tools_response = await client.get(f"/api/mcp/{session_id}/tools")
    assert tools_response.status_code == 200, tools_response.text
    tool_names = {tool["name"] for tool in tools_response.json()["tools"]}
    assert "fetch" in tool_names

    call_response = await client.post(
        f"/api/mcp/{session_id}/call",
        json={
            "tool_name": "fetch",
            "arguments": {"url": "https://example.com"},
        },
    )
    assert call_response.status_code == 200, call_response.text
    text = "\n".join(
        item.get("text", "") for item in call_response.json()["content"]
    )
    assert "Example Domain" in text

    delete_response = await client.delete(f"/api/mcp/{session_id}")
    assert delete_response.status_code == 200

    missing_response = await client.get(f"/api/mcp/{session_id}/tools")
    assert missing_response.status_code == 404


@pytest.mark.asyncio
async def test_startup_failure_returns_400(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/api/mcp/connect",
        json={"server_command": ["definitely-not-a-real-mcp-command"]},
    )
    assert response.status_code == 400
    assert "MCP Server 启动失败" in response.text


@pytest.mark.asyncio
async def test_rejects_shell_metacharacters(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/api/mcp/connect",
        json={"server_command": ["npx", "-y", "bad;command"]},
    )
    assert response.status_code == 400
    assert "shell" in response.text


@pytest.mark.asyncio
async def test_connection_rate_limit(client: httpx.AsyncClient) -> None:
    for _ in range(5):
        response = await client.post(
            "/api/mcp/connect",
            json={"server_command": ["npx", "-y", "bad;command"]},
        )
        assert response.status_code == 400

    limited = await client.post(
        "/api/mcp/connect",
        json={"server_command": ["npx", "-y", "bad;command"]},
    )
    assert limited.status_code == 429
