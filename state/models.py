from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Mapping


class WorkflowStatus(StrEnum):
    RECEIVED = "received"
    DIAGNOSING = "diagnosing"
    PLANNED = "planned"
    WAITING_APPROVAL = "waiting_approval"
    EXECUTING = "executing"
    VERIFYING = "verifying"
    SUCCEEDED = "succeeded"
    ROLLED_BACK = "rolled_back"
    ESCALATED = "escalated"
    FAILED = "failed"


@dataclass(frozen=True)
class ServiceRecord:
    service_id: str
    owner: str
    tier: int = 3
    repositories: tuple[str, ...] = ()
    dependencies: tuple[str, ...] = ()
    slo_target: float | None = None
    autonomy_level: int = 0
    metadata: Mapping[str, str] = field(default_factory=dict)
    version: int = 1


@dataclass(frozen=True)
class WorkflowRecord:
    workflow_id: str
    service_id: str
    environment: str
    kind: str
    status: WorkflowStatus
    correlation_id: str
    plan_hash: str | None = None
    version: int = 1
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass(frozen=True)
class AuditEvent:
    event_id: str
    correlation_id: str
    actor: str
    action: str
    resource: str
    payload: Mapping[str, object]
    occurred_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    previous_hash: str | None = None
    event_hash: str | None = None
