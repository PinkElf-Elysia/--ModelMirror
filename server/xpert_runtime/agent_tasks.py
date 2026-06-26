from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Literal

from .events import RuntimeEventStore

AgentTaskStatus = Literal["pending", "running", "completed", "failed", "cancelled"]
AgentHandoffStatus = Literal["pending", "accepted", "rejected", "completed"]
HANDOFF_TRANSITIONS: dict[AgentHandoffStatus, set[AgentHandoffStatus]] = {
    "pending": {"accepted", "rejected"},
    "accepted": {"completed"},
    "rejected": set(),
    "completed": set(),
}


@dataclass(slots=True)
class AgentTask:
    task_id: str
    title: str
    input: str
    status: AgentTaskStatus = "pending"
    result: str | None = None
    error: str | None = None
    source_agent: str | None = None
    assigned_agent: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def touch(self) -> None:
        self.updated_at = time.time()


@dataclass(slots=True)
class AgentHandoff:
    handoff_id: str
    task_id: str
    source_agent: str
    target_agent: str
    reason: str
    status: AgentHandoffStatus = "pending"
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def touch(self) -> None:
        self.updated_at = time.time()


class AgentTaskStore:
    """In-memory agent task store for Xpert-aligned runtime work."""

    def __init__(self, event_store: RuntimeEventStore | None = None) -> None:
        self._lock = asyncio.Lock()
        self._tasks: dict[str, AgentTask] = {}
        self._handoffs: list[AgentHandoff] = []
        self._event_store = event_store

    async def create_task(
        self,
        title: str,
        input_text: str,
        *,
        source_agent: str | None = None,
        assigned_agent: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AgentTask:
        task = AgentTask(
            task_id=str(uuid.uuid4()),
            title=title,
            input=input_text,
            source_agent=source_agent,
            assigned_agent=assigned_agent,
            metadata=dict(metadata or {}),
        )
        async with self._lock:
            self._tasks[task.task_id] = task
        await self._record(
            "agent.task.created",
            task_id=task.task_id,
            payload={
                "task_id": task.task_id,
                "title": task.title,
                "source_agent": source_agent,
                "assigned_agent": assigned_agent,
            },
        )
        return task

    async def get_task(self, task_id: str) -> AgentTask | None:
        async with self._lock:
            return self._tasks.get(task_id)

    async def list_tasks(
        self,
        *,
        status: AgentTaskStatus | None = None,
        limit: int = 50,
    ) -> list[AgentTask]:
        async with self._lock:
            tasks = list(self._tasks.values())
        if status is not None:
            tasks = [task for task in tasks if task.status == status]
        tasks.sort(key=lambda task: task.created_at, reverse=True)
        return tasks[: max(1, limit)]

    async def update_task(
        self,
        task_id: str,
        *,
        status: AgentTaskStatus | None = None,
        result: str | None = None,
        error: str | None = None,
        assigned_agent: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AgentTask:
        async with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                raise KeyError(f"Agent task not found: {task_id}")
            if status is not None:
                task.status = status
            if result is not None:
                task.result = result
            if error is not None:
                task.error = error
            if assigned_agent is not None:
                task.assigned_agent = assigned_agent
            if metadata is not None:
                task.metadata.update(metadata)
            task.touch()
            updated = task
        await self._record(
            "agent.task.updated",
            task_id=task_id,
            payload={
                "task_id": task_id,
                "status": updated.status,
                "has_result": updated.result is not None,
                "has_error": updated.error is not None,
            },
        )
        return updated

    async def cancel_task(self, task_id: str, reason: str = "cancelled") -> AgentTask:
        task = await self.update_task(task_id, status="cancelled", error=reason)
        await self._record(
            "agent.task.cancelled",
            task_id=task_id,
            payload={"task_id": task_id, "reason": reason},
        )
        return task

    async def create_handoff(
        self,
        task_id: str,
        source_agent: str,
        target_agent: str,
        reason: str,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> AgentHandoff:
        handoff = AgentHandoff(
            handoff_id=str(uuid.uuid4()),
            task_id=task_id,
            source_agent=source_agent,
            target_agent=target_agent,
            reason=reason,
            metadata=dict(metadata or {}),
        )
        async with self._lock:
            self._handoffs.append(handoff)
        await self._record(
            "agent.handoff.created",
            task_id=task_id,
            payload={
                "handoff_id": handoff.handoff_id,
                "task_id": task_id,
                "source_agent": source_agent,
                "target_agent": target_agent,
            },
        )
        return handoff

    async def list_handoffs(self, task_id: str | None = None) -> list[AgentHandoff]:
        async with self._lock:
            handoffs = list(self._handoffs)
        if task_id is not None:
            handoffs = [handoff for handoff in handoffs if handoff.task_id == task_id]
        handoffs.sort(key=lambda handoff: handoff.created_at, reverse=True)
        return handoffs

    async def get_handoff(self, handoff_id: str) -> AgentHandoff | None:
        async with self._lock:
            for handoff in self._handoffs:
                if handoff.handoff_id == handoff_id:
                    return handoff
        return None

    async def update_handoff_status(
        self,
        handoff_id: str,
        status: AgentHandoffStatus,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> AgentHandoff:
        async with self._lock:
            handoff = next(
                (
                    item
                    for item in self._handoffs
                    if item.handoff_id == handoff_id
                ),
                None,
            )
            if handoff is None:
                raise KeyError(f"Agent handoff not found: {handoff_id}")
            allowed = HANDOFF_TRANSITIONS.get(handoff.status, set())
            if status not in allowed:
                raise ValueError(
                    f"Invalid handoff transition: {handoff.status} -> {status}"
                )
            handoff.status = status
            if metadata is not None:
                handoff.metadata.update(metadata)
            handoff.touch()
            updated = handoff
        await self._record(
            f"agent.handoff.{status}",
            task_id=updated.task_id,
            payload={
                "handoff_id": updated.handoff_id,
                "task_id": updated.task_id,
                "source_agent": updated.source_agent,
                "target_agent": updated.target_agent,
                "status": updated.status,
            },
        )
        return updated

    async def _record(
        self,
        event_type: str,
        *,
        task_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> None:
        if self._event_store is None:
            return
        try:
            await self._event_store.record_event(
                event_type,
                task_id=task_id,
                payload=payload or {},
                severity="info",
            )
        except Exception:
            return
