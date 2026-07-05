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
                "id": "task",
                "type": "agent_task",
                "data": {
                    "kind": "agent_task",
                    "title": "Create task",
                    "taskTitle": "规划 {{user_input}}",
                    "taskInput": "请拆解任务：{{user_input}}",
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
            {"id": "e1", "source": "input", "target": "task"},
            {"id": "e2", "source": "task", "target": "output"},
        ],
    }

    response = await client.post(
        "/api/workflow/run",
        json={
            "workflow": workflow,
            "inputs": {"user_input": "准备 Xpert 对齐计划"},
        },
    )

    assert response.status_code == 200, response.text
    events = _parse_sse_events(response.text)
    workflow_meta = next(event for event in events if event.get("event") == "workflow_meta")
    workflow_run_id = workflow_meta["run_id"]
    task_node_end = next(
        event
        for event in events
        if event.get("event") == "node_end" and event.get("node_id") == "task"
    )
    agent_task_id = task_node_end["output"]

    task_response = await client.get(f"/api/runtime/agent-tasks/{agent_task_id}")
    assert task_response.status_code == 200, task_response.text
    task = task_response.json()

    assert task["title"] == "规划 准备 Xpert 对齐计划"
    assert task["input"] == "请拆解任务：准备 Xpert 对齐计划"
    assert task["status"] == "pending"
    assert task["source_agent"] == "workflow"
    assert task["assigned_agent"] == "workflow-planner"
    assert task["metadata"]["workflow_id"] == "agent-task-workflow"
    assert task["metadata"]["node_id"] == "task"

    workflow_end = next(event for event in events if event.get("event") == "workflow_end")
    assert workflow_end["final_output"] == agent_task_id
    assert workflow_end["run_id"] == workflow_run_id

    workflow_run_response = await client.get(f"/api/runtime/runs/{workflow_run_id}")
    assert workflow_run_response.status_code == 200, workflow_run_response.text
    workflow_run = workflow_run_response.json()
    assert workflow_run["run_type"] == "workflow"
    assert workflow_run["status"] == "completed"
    assert workflow_run["metadata"]["workflow_task_id"] == workflow_meta["task_id"]

    task_runs_response = await client.get("/api/runtime/runs?run_type=agent_task&limit=50")
    assert task_runs_response.status_code == 200, task_runs_response.text
    task_runs = task_runs_response.json()
    assert any(
        run["source_id"] == agent_task_id
        and run["parent_run_id"] == workflow_run_id
        and run["metadata"]["node_id"] == "task"
        for run in task_runs
    )


@pytest.mark.asyncio
async def test_workflow_agent_handoff_node_creates_handoff(
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
                "id": "task",
                "type": "agent_task",
                "data": {
                    "kind": "agent_task",
                    "title": "Create task",
                    "taskTitle": "Plan {{user_input}}",
                    "taskInput": "Please plan: {{user_input}}",
                    "assignedAgent": "workflow-planner",
                    "outputVariable": "agent_task_id",
                },
            },
            {
                "id": "handoff",
                "type": "agent_handoff",
                "data": {
                    "kind": "agent_handoff",
                    "title": "Create handoff",
                    "taskIdVariable": "agent_task_id",
                    "targetAgent": "reviewer-agent",
                    "sourceAgent": "workflow",
                    "reason": "Please review {{user_input}}",
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
            {"id": "e1", "source": "input", "target": "task"},
            {"id": "e2", "source": "task", "target": "handoff"},
            {"id": "e3", "source": "handoff", "target": "output"},
        ],
    }

    response = await client.post(
        "/api/workflow/run",
        json={
            "workflow": workflow,
            "inputs": {"user_input": "prepare Xpert handoff"},
        },
    )

    assert response.status_code == 200, response.text
    events = _parse_sse_events(response.text)
    workflow_meta = next(event for event in events if event.get("event") == "workflow_meta")
    workflow_run_id = workflow_meta["run_id"]
    task_node_end = next(
        event
        for event in events
        if event.get("event") == "node_end" and event.get("node_id") == "task"
    )
    handoff_node_end = next(
        event
        for event in events
        if event.get("event") == "node_end" and event.get("node_id") == "handoff"
    )
    agent_task_id = task_node_end["output"]
    agent_handoff_id = handoff_node_end["output"]

    assert agent_handoff_id
    handoffs_response = await client.get(
        f"/api/runtime/agent-tasks/{agent_task_id}/handoffs"
    )
    assert handoffs_response.status_code == 200, handoffs_response.text
    handoffs = handoffs_response.json()
    assert any(
        handoff["handoff_id"] == agent_handoff_id
        and handoff["target_agent"] == "reviewer-agent"
        and handoff["status"] == "pending"
        for handoff in handoffs
    )

    workflow_end = next(event for event in events if event.get("event") == "workflow_end")
    assert workflow_end["final_output"] == agent_handoff_id
    assert workflow_end["run_id"] == workflow_run_id

    workflow_run_response = await client.get(f"/api/runtime/runs/{workflow_run_id}")
    assert workflow_run_response.status_code == 200, workflow_run_response.text
    assert workflow_run_response.json()["status"] == "completed"

    task_runs_response = await client.get("/api/runtime/runs?run_type=agent_task&limit=50")
    handoff_runs_response = await client.get(
        "/api/runtime/runs?run_type=agent_handoff&limit=50"
    )
    assert task_runs_response.status_code == 200, task_runs_response.text
    assert handoff_runs_response.status_code == 200, handoff_runs_response.text
    task_runs = task_runs_response.json()
    handoff_runs = handoff_runs_response.json()
    assert any(
        run["source_id"] == agent_task_id
        and run["parent_run_id"] == workflow_run_id
        for run in task_runs
    )
    assert any(
        run["source_id"] == agent_handoff_id
        and run["parent_run_id"] == workflow_run_id
        and run["metadata"]["target_agent"] == "reviewer-agent"
        for run in handoff_runs
    )


def _parse_sse_events(sse_text: str) -> list[dict]:
    events: list[dict] = []
    for line in sse_text.splitlines():
        if not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if not payload:
            continue
        events.append(json.loads(payload))
    return events
