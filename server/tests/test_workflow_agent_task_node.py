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
    workflow_meta = next(event for event in events if event.get("event") == "workflow_meta")
    workflow_run_id = workflow_meta.get("run_id")
    assert isinstance(workflow_run_id, str)
    assert workflow_run_id

    workflow_end = next(event for event in events if event.get("event") == "workflow_end")
    assert workflow_end.get("run_id") == workflow_run_id

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

    workflow_run_response = await client.get(f"/api/runtime/runs/{workflow_run_id}")
    assert workflow_run_response.status_code == 200
    workflow_run = workflow_run_response.json()
    assert workflow_run["run_type"] == "workflow"
    assert workflow_run["status"] == "completed"
    assert workflow_run["metadata"]["workflow_task_id"]

    agent_task_runs_response = await client.get(
        "/api/runtime/runs?run_type=agent_task&limit=50",
    )
    assert agent_task_runs_response.status_code == 200
    agent_task_runs = agent_task_runs_response.json()
    agent_task_run = next(item for item in agent_task_runs if item["source_id"] == task_id)
    assert agent_task_run["parent_run_id"] == workflow_run_id
    assert agent_task_run["metadata"]["node_id"] == "agent_task"


@pytest.mark.asyncio
async def test_workflow_agent_handoff_node_creates_runtime_handoff_and_runs(
    client: httpx.AsyncClient,
) -> None:
    workflow = {
        "id": "agent-handoff-workflow",
        "title": "agent handoff workflow",
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
                "id": "agent_handoff",
                "type": "agent_handoff",
                "data": {
                    "kind": "agent_handoff",
                    "title": "Handoff agent task",
                    "taskIdVariable": "agent_task_id",
                    "sourceAgent": "workflow-planner",
                    "targetAgent": "review-agent",
                    "reason": "Review plan for {{user_input}}",
                    "outputVariable": "agent_handoff_id",
                },
            },
            {
                "id": "output",
                "type": "output",
                "data": {"kind": "output", "outputVariable": "agent_handoff_id"},
            },
        ],
        "edges": [
            {"id": "e1", "source": "input", "target": "agent_task"},
            {"id": "e2", "source": "agent_task", "target": "agent_handoff"},
            {"id": "e3", "source": "agent_handoff", "target": "output"},
        ],
    }

    response = await client.post(
        "/api/workflow/run",
        json={
            "workflow": workflow,
            "inputs": {"user_input": "handoff scenario"},
        },
    )
    assert response.status_code == 200, response.text

    events = _parse_sse_events(response.text)
    workflow_meta = next(event for event in events if event.get("event") == "workflow_meta")
    workflow_run_id = workflow_meta.get("run_id")
    assert isinstance(workflow_run_id, str)

    task_end = next(
        event
        for event in events
        if event.get("event") == "node_end" and event.get("node_id") == "agent_task"
    )
    task_id = task_end.get("output")
    assert isinstance(task_id, str)
    assert task_id

    handoff_end = next(
        event
        for event in events
        if event.get("event") == "node_end" and event.get("node_id") == "agent_handoff"
    )
    handoff_id = handoff_end.get("output")
    assert isinstance(handoff_id, str)
    assert handoff_id
    assert handoff_end["variables"]["agent_handoff_id"] == handoff_id

    handoff_response = await client.get(f"/api/runtime/agent-tasks/{task_id}/handoffs")
    assert handoff_response.status_code == 200, handoff_response.text
    handoffs = handoff_response.json()
    assert any(item["handoff_id"] == handoff_id for item in handoffs)

    task_runs_response = await client.get("/api/runtime/runs?run_type=agent_task&limit=50")
    assert task_runs_response.status_code == 200
    task_runs = task_runs_response.json()
    task_run = next(item for item in task_runs if item["source_id"] == task_id)
    assert task_run["parent_run_id"] == workflow_run_id

    handoff_runs_response = await client.get(
        "/api/runtime/runs?run_type=agent_handoff&limit=50",
    )
    assert handoff_runs_response.status_code == 200
    handoff_runs = handoff_runs_response.json()
    handoff_run = next(item for item in handoff_runs if item["source_id"] == handoff_id)
    assert handoff_run["parent_run_id"] == workflow_run_id
    assert handoff_run["metadata"]["agent_task_id"] == task_id
    assert handoff_run["metadata"]["target_agent"] == "review-agent"

    child_runs_response = await client.get(
        f"/api/runtime/runs?parent_run_id={workflow_run_id}&limit=50",
    )
    assert child_runs_response.status_code == 200, child_runs_response.text
    child_runs = child_runs_response.json()
    assert any(
        item["run_type"] == "agent_task" and item["source_id"] == task_id
        for item in child_runs
    )
    assert any(
        item["run_type"] == "agent_handoff" and item["source_id"] == handoff_id
        for item in child_runs
    )


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
