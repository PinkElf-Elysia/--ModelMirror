from __future__ import annotations

import httpx
import pytest
import pytest_asyncio

from server.xpert_runtime import AgentTaskStore, RuntimeEventStore


@pytest.mark.asyncio
async def test_create_and_get_task() -> None:
    store = AgentTaskStore()
    task = await store.create_task("Test Task", "do something")

    assert task.task_id
    assert task.title == "Test Task"
    assert task.input == "do something"
    assert task.status == "pending"

    got = await store.get_task(task.task_id)
    assert got is not None
    assert got.task_id == task.task_id

    assert await store.get_task("nonexistent") is None


@pytest.mark.asyncio
async def test_update_task() -> None:
    store = AgentTaskStore()
    task = await store.create_task("T", "in")

    updated = await store.update_task(task.task_id, status="running")
    assert updated.status == "running"
    assert updated.updated_at >= task.created_at

    finished = await store.update_task(
        task.task_id,
        status="completed",
        result="done",
    )
    assert finished.status == "completed"
    assert finished.result == "done"


@pytest.mark.asyncio
async def test_cancel_task() -> None:
    store = AgentTaskStore()
    task = await store.create_task("T", "in")

    cancelled = await store.cancel_task(task.task_id, reason="user cancelled")

    assert cancelled.status == "cancelled"
    assert cancelled.error == "user cancelled"


@pytest.mark.asyncio
async def test_list_tasks_with_status_filter() -> None:
    store = AgentTaskStore()
    t1 = await store.create_task("A", "a")
    await store.create_task("B", "b")
    await store.update_task(t1.task_id, status="completed")

    all_tasks = await store.list_tasks()
    assert len(all_tasks) == 2
    assert all_tasks[0].created_at >= all_tasks[1].created_at

    completed = await store.list_tasks(status="completed")
    assert len(completed) == 1
    assert completed[0].task_id == t1.task_id


@pytest.mark.asyncio
async def test_handoff_create_and_list() -> None:
    store = AgentTaskStore()
    task = await store.create_task("T", "in")

    handoff = await store.create_handoff(
        task.task_id,
        source_agent="agent_a",
        target_agent="agent_b",
        reason="need expertise",
    )

    assert handoff.handoff_id
    assert handoff.status == "pending"

    all_handoffs = await store.list_handoffs()
    assert len(all_handoffs) == 1

    task_handoffs = await store.list_handoffs(task_id=task.task_id)
    assert len(task_handoffs) == 1

    other = await store.list_handoffs(task_id="other")
    assert other == []


@pytest.mark.asyncio
async def test_event_store_records_task_events() -> None:
    event_store = RuntimeEventStore()
    store = AgentTaskStore(event_store=event_store)

    task = await store.create_task("ET", "input")
    await store.cancel_task(task.task_id)

    events = await event_store.list_events()
    event_types = [event.type for event in events]
    assert "agent.task.created" in event_types
    assert "agent.task.cancelled" in event_types
    assert "agent.task.updated" in event_types


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
async def test_api_create_task(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/api/runtime/agent-tasks",
        json={"title": "API Task", "input": "hello"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "API Task"
    assert data["status"] == "pending"
    assert "task_id" in data


@pytest.mark.asyncio
async def test_api_create_task_missing_title(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/api/runtime/agent-tasks",
        json={"input": "hello"},
    )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_api_get_task_404(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/runtime/agent-tasks/nonexistent")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_api_cancel_task(client: httpx.AsyncClient) -> None:
    create_response = await client.post(
        "/api/runtime/agent-tasks",
        json={"title": "Cancel Test", "input": "x"},
    )
    task_id = create_response.json()["task_id"]

    cancel_response = await client.post(
        f"/api/runtime/agent-tasks/{task_id}/cancel",
        json={"reason": "test cancel"},
    )

    assert cancel_response.status_code == 200
    data = cancel_response.json()
    assert data["status"] == "cancelled"
    assert data["error"] == "test cancel"


@pytest.mark.asyncio
async def test_api_list_tasks(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/runtime/agent-tasks")

    assert response.status_code == 200
    assert isinstance(response.json(), list)
