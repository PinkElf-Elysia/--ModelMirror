from __future__ import annotations

import httpx
import pytest
import pytest_asyncio

from server.main import app
from server.xpert_runtime import RunRegistry


@pytest_asyncio.fixture
async def client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as async_client:
        yield async_client


@pytest.mark.asyncio
async def test_run_registry_create_and_get_run() -> None:
    registry = RunRegistry()
    run = await registry.create_run(
        "workflow",
        "Test workflow",
        status="running",
        source_id="workflow-1",
        metadata={"node_count": 2},
    )

    assert run.run_id
    assert run.run_type == "workflow"
    assert run.status == "running"
    assert run.metadata["node_count"] == 2

    got = await registry.get_run(run.run_id)
    assert got is not None
    assert got.run_id == run.run_id
    assert await registry.get_run("missing") is None


@pytest.mark.asyncio
async def test_run_registry_list_filters_and_limit() -> None:
    registry = RunRegistry()
    await registry.create_run("workflow", "A", status="completed")
    await registry.create_run("agent_task", "B", status="pending")
    await registry.create_run("agent_task", "C", status="completed")

    agent_runs = await registry.list_runs(run_type="agent_task")
    assert len(agent_runs) == 2
    assert all(run.run_type == "agent_task" for run in agent_runs)

    completed_runs = await registry.list_runs(status="completed")
    assert len(completed_runs) == 2

    limited = await registry.list_runs(limit=1)
    assert len(limited) == 1


@pytest.mark.asyncio
async def test_run_registry_filters_by_parent_and_source() -> None:
    registry = RunRegistry()
    parent = await registry.create_run("workflow", "Parent", status="running")
    child = await registry.create_run(
        "agent_handoff",
        "Child handoff",
        parent_run_id=parent.run_id,
        source_id="handoff-filter-source",
    )
    await registry.create_run(
        "agent_task",
        "Other child",
        parent_run_id="other-parent",
        source_id="other-source",
    )

    children = await registry.list_runs(parent_run_id=parent.run_id)
    assert [run.run_id for run in children] == [child.run_id]

    source_runs = await registry.list_runs(source_id="handoff-filter-source")
    assert [run.run_id for run in source_runs] == [child.run_id]


@pytest.mark.asyncio
async def test_run_registry_cancel_run_updates_status() -> None:
    registry = RunRegistry()
    run = await registry.create_run("agent_handoff", "handoff", status="pending")

    cancelled = await registry.cancel_run(run.run_id, reason="manual stop")

    assert cancelled.status == "cancelled"
    assert cancelled.error == "manual stop"
    assert cancelled.cancelled_at is not None
    assert cancelled.metadata["cancel_reason"] == "manual stop"


@pytest.mark.asyncio
async def test_runtime_run_api_missing_run_returns_404(
    client: httpx.AsyncClient,
) -> None:
    response = await client.get("/api/runtime/runs/missing-run-id")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_runtime_run_api_list_and_cancel(client: httpx.AsyncClient) -> None:
    create_task = await client.post(
        "/api/runtime/agent-tasks",
        json={"title": "Run API Task", "input": "hello"},
    )
    assert create_task.status_code == 200, create_task.text
    task_id = create_task.json()["task_id"]

    list_response = await client.get("/api/runtime/runs?run_type=agent_task&limit=20")
    assert list_response.status_code == 200, list_response.text
    runs = list_response.json()
    run = next(item for item in runs if item["source_id"] == task_id)

    cancel_response = await client.post(
        f"/api/runtime/runs/{run['run_id']}/cancel",
        json={"reason": "api test"},
    )
    assert cancel_response.status_code == 200, cancel_response.text
    cancelled = cancel_response.json()
    assert cancelled["status"] == "cancelled"
    assert cancelled["error"] == "api test"


@pytest.mark.asyncio
async def test_runtime_run_api_filters_parent_and_source(
    client: httpx.AsyncClient,
) -> None:
    from server.main import run_registry

    parent = await run_registry.create_run(
        "workflow",
        "API parent workflow",
        status="running",
        source_id="api-parent-workflow",
    )
    child = await run_registry.create_run(
        "agent_task",
        "API child task",
        parent_run_id=parent.run_id,
        source_id="api-child-source",
    )
    await run_registry.create_run(
        "agent_handoff",
        "API unrelated handoff",
        parent_run_id="different-parent",
        source_id="api-unrelated-source",
    )

    parent_response = await client.get(
        f"/api/runtime/runs?parent_run_id={parent.run_id}&limit=20",
    )
    assert parent_response.status_code == 200, parent_response.text
    parent_runs = parent_response.json()
    assert any(item["run_id"] == child.run_id for item in parent_runs)
    assert all(item["parent_run_id"] == parent.run_id for item in parent_runs)

    source_response = await client.get(
        "/api/runtime/runs?source_id=api-child-source&limit=20",
    )
    assert source_response.status_code == 200, source_response.text
    source_runs = source_response.json()
    assert [item["run_id"] for item in source_runs] == [child.run_id]
