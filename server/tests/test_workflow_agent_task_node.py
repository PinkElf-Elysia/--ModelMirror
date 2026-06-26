from __future__ import annotations

import json

import httpx
import pytest
import pytest_asyncio

from server.main import app


@pytest_asyncio.fixture
async def client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as async_client:
        yield async_client


@pytest.mark.asyncio
async def test_workflow_agent_task_node_creates_runtime_task(
    client: httpx.AsyncClient,
) -> None:
    workflow = {
        "id": "agent-task-workflow",
        "title": "agent task workflow",
        "nodes": [
            {
                "id": "input",
                "type": "input",
                "data": {"kind": "input", "variableName": "user_input"},
            },
            {
                "id": "agent_task",
                "type": "agent_task",
                "data": {
                    "kind": "agent_task",
                    "title": "Create agent task",
                    "taskTitle": "Plan {{user_input}}",
                    "taskInput": "Please plan: {{user_input}}",
                    "assignedAgent": "workflow-planner",
                    "outputVariable": "agent_task_id",
                },
            },
            {
                "id": "output",
                "type": "output",
                "data": {"kind": "output", "outputVariable": "agent_task_id"},
            },
        ],
        "edges": [
            {"id": "e1", "source": "input", "target": "agent_task"},
            {"id": "e2", "source": "agent_task", "target": "output"},
        ],
    }

    response = await client.post(
        "/api/workflow/run",
        json={
            "workflow": workflow,
            "inputs": {"user_input": "launch a support workflow"},
        },
    )
    assert response.status_code == 200, response.text

    events = _parse_sse_events(response.text)
    agent_task_end = next(
        event
        for event in events
        if event.get("event") == "node_end" and event.get("node_id") == "agent_task"
    )
    task_id = agent_task_end.get("output")
    assert isinstance(task_id, str)
    assert task_id
    assert agent_task_end["variables"]["agent_task_id"] == task_id

    deltas = [
        event
        for event in events
        if event.get("event") == "node_delta" and event.get("node_id") == "agent_task"
    ]
    assert any("Agent Task" in str(event.get("output")) for event in deltas)

    detail_response = await client.get(f"/api/runtime/agent-tasks/{task_id}")
    assert detail_response.status_code == 200, detail_response.text
    payload = detail_response.json()
    assert payload["task_id"] == task_id
    assert payload["title"] == "Plan launch a support workflow"
    assert payload["input"] == "Please plan: launch a support workflow"
    assert payload["source_agent"] == "workflow"
    assert payload["assigned_agent"] == "workflow-planner"
    assert payload["metadata"]["workflow_id"] == "agent-task-workflow"
    assert payload["metadata"]["workflow_node_id"] == "agent_task"


def _parse_sse_events(sse_text: str) -> list[dict]:
    events: list[dict] = []
    for line in sse_text.splitlines():
        if not line.startswith("data:"):
            continue
        try:
            payload = json.loads(line[5:].strip())
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            events.append(payload)
    return events
