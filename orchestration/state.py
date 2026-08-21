from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum


class WorkflowStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class WorkflowState:
    workflow_id: str
    service: str
    environment: str
    plan_hash: str
    status: WorkflowStatus = WorkflowStatus.PENDING
    step: str = "created"
    attempts: int = 0
    last_error: str | None = None

    def transition(self, *, status: WorkflowStatus, step: str, error: str | None = None) -> "WorkflowState":
        return replace(
            self,
            status=status,
            step=step,
            attempts=self.attempts + 1,
            last_error=error,
        )
