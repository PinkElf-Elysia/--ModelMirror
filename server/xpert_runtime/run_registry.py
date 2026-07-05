from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Literal

RuntimeRunType = Literal["workflow", "agent_task", "agent_handoff"]
RuntimeRunStatus = Literal["pending", "running", "completed", "failed", "cancelled"]


@dataclass(slots=True)
class RuntimeRun:
    """In-memory run record for Xpert-aligned workflow and agent execution."""

    run_id: str
    run_type: RuntimeRunType
    status: RuntimeRunStatus
    title: str
    source_id: str | None = None
    parent_run_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    cancelled_at: float | None = None
    error: str | None = None

    def touch(self) -> None:
        self.updated_at = time.time()


class RunRegistry:
    """Small in-memory RunRegistry for workflow, AgentTask, and Handoff runs."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._runs: dict[str, RuntimeRun] = {}

    async def create_run(
        self,
        run_type: RuntimeRunType,
        title: str,
        *,
        status: RuntimeRunStatus = "pending",
        source_id: str | None = None,
        parent_run_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> RuntimeRun:
        run = RuntimeRun(
            run_id=str(uuid.uuid4()),
            run_type=run_type,
            status=status,
            title=title,
            source_id=source_id,
            parent_run_id=parent_run_id,
            metadata=dict(metadata or {}),
        )
        async with self._lock:
            self._runs[run.run_id] = run
        return run

    async def get_run(self, run_id: str) -> RuntimeRun | None:
        async with self._lock:
            return self._runs.get(run_id)

    async def list_runs(
        self,
        *,
        run_type: RuntimeRunType | None = None,
        status: RuntimeRunStatus | None = None,
        limit: int = 50,
    ) -> list[RuntimeRun]:
        async with self._lock:
            runs = list(self._runs.values())
        if run_type is not None:
            runs = [run for run in runs if run.run_type == run_type]
        if status is not None:
            runs = [run for run in runs if run.status == status]
        runs.sort(key=lambda run: run.created_at, reverse=True)
        return runs[: max(1, limit)]

    async def update_run(
        self,
        run_id: str,
        *,
        status: RuntimeRunStatus | None = None,
        error: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> RuntimeRun:
        async with self._lock:
            run = self._runs.get(run_id)
            if run is None:
                raise KeyError(f"Runtime run not found: {run_id}")
            if status is not None:
                run.status = status
                if status == "cancelled" and run.cancelled_at is None:
                    run.cancelled_at = time.time()
            if error is not None:
                run.error = error
            if metadata is not None:
                run.metadata.update(metadata)
            run.touch()
            return run

    async def cancel_run(
        self,
        run_id: str,
        *,
        reason: str = "cancelled",
    ) -> RuntimeRun:
        return await self.update_run(
            run_id,
            status="cancelled",
            error=reason,
            metadata={"cancel_reason": reason},
        )
