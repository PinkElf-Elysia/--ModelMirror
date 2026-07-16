from __future__ import annotations

from typing import Any


class RuntimeInterrupt(Exception):
    """Non-fail-open signal used to suspend a durable runtime execution."""

    def __init__(
        self,
        approval_id: str,
        *,
        task_id: str,
        run_id: str,
        continuation: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(f"Runtime approval required: {approval_id}")
        self.approval_id = approval_id
        self.task_id = task_id
        self.run_id = run_id
        self.continuation = dict(continuation or {})


class RuntimeMiddlewareFatalError(Exception):
    """Middleware error that must never fall back to executing a provider."""
