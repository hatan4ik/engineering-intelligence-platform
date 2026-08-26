"""Canonical, versioned workflow-lifecycle transition contract.

Temporal activities are delivered at least once.  A lifecycle event therefore
contains the optimistic version and an idempotency key needed to make a retry,
worker restart, or response-loss replay safe at the authoritative-state
boundary.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import Mapping

from state.models import WorkflowRecord, WorkflowStatus


LIFECYCLE_SCHEMA_VERSION = 1
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@-]{0,191}$")
_PLAN_HASH = re.compile(r"^sha256:[a-f0-9]{64}$")


class LifecycleContractError(ValueError):
    """Raised when an event cannot represent a safe lifecycle transition."""


_ALLOWED_TRANSITIONS: dict[WorkflowStatus | None, frozenset[WorkflowStatus]] = {
    None: frozenset({WorkflowStatus.RECEIVED}),
    WorkflowStatus.RECEIVED: frozenset({
        WorkflowStatus.DIAGNOSING,
        WorkflowStatus.PLANNED,
        WorkflowStatus.FAILED,
        WorkflowStatus.ESCALATED,
        WorkflowStatus.CANCELLED,
    }),
    WorkflowStatus.DIAGNOSING: frozenset({
        WorkflowStatus.PLANNED,
        WorkflowStatus.FAILED,
        WorkflowStatus.ESCALATED,
        WorkflowStatus.CANCELLED,
    }),
    WorkflowStatus.PLANNED: frozenset({
        WorkflowStatus.WAITING_APPROVAL,
        WorkflowStatus.EXECUTING,
        WorkflowStatus.SUCCEEDED,
        WorkflowStatus.FAILED,
        WorkflowStatus.ESCALATED,
        WorkflowStatus.CANCELLED,
    }),
    WorkflowStatus.WAITING_APPROVAL: frozenset({
        WorkflowStatus.EXECUTING,
        WorkflowStatus.FAILED,
        WorkflowStatus.ESCALATED,
        WorkflowStatus.CANCELLED,
    }),
    WorkflowStatus.EXECUTING: frozenset({
        WorkflowStatus.VERIFYING,
        WorkflowStatus.ROLLED_BACK,
        WorkflowStatus.FAILED,
        WorkflowStatus.ESCALATED,
        WorkflowStatus.CANCELLED,
    }),
    WorkflowStatus.VERIFYING: frozenset({
        WorkflowStatus.SUCCEEDED,
        WorkflowStatus.ROLLED_BACK,
        WorkflowStatus.FAILED,
        WorkflowStatus.ESCALATED,
    }),
    WorkflowStatus.SUCCEEDED: frozenset(),
    WorkflowStatus.ROLLED_BACK: frozenset(),
    WorkflowStatus.ESCALATED: frozenset(),
    WorkflowStatus.FAILED: frozenset(),
    WorkflowStatus.CANCELLED: frozenset(),
}


@dataclass(frozen=True)
class WorkflowLifecycleEvent:
    """The only event shape accepted by the durable state/audit bridge."""

    event_id: str
    idempotency_key: str
    workflow_id: str
    tenant_id: str
    service_id: str
    environment: str
    kind: str
    correlation_id: str
    actor: str
    action: str
    from_status: WorkflowStatus | None
    to_status: WorkflowStatus
    expected_version: int | None
    plan_hash: str | None = None
    causation_id: str | None = None
    consequential: bool = False
    attributes: Mapping[str, object] = field(default_factory=dict)
    occurred_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    schema_version: int = LIFECYCLE_SCHEMA_VERSION

    def validate(self) -> None:
        for label, value in (
            ("event_id", self.event_id),
            ("idempotency_key", self.idempotency_key),
            ("workflow_id", self.workflow_id),
            ("tenant_id", self.tenant_id),
            ("service_id", self.service_id),
            ("environment", self.environment),
            ("kind", self.kind),
            ("correlation_id", self.correlation_id),
            ("actor", self.actor),
            ("action", self.action),
        ):
            if not _IDENTIFIER.fullmatch(value):
                raise LifecycleContractError(f"{label} must be a bounded opaque identifier")
        if self.causation_id is not None and not _IDENTIFIER.fullmatch(self.causation_id):
            raise LifecycleContractError("causation_id must be a bounded opaque identifier when set")
        if self.schema_version != LIFECYCLE_SCHEMA_VERSION:
            raise LifecycleContractError("unsupported workflow lifecycle schema version")
        if self.plan_hash is not None and not _PLAN_HASH.fullmatch(self.plan_hash):
            raise LifecycleContractError("plan_hash must be a sha256 digest when set")
        if type(self.consequential) is not bool:
            raise LifecycleContractError("consequential must be boolean")
        if self.expected_version is not None and (type(self.expected_version) is not int or self.expected_version < 1):
            raise LifecycleContractError("expected_version must be a positive integer when set")
        if self.from_status is None:
            if self.expected_version is not None or self.to_status is not WorkflowStatus.RECEIVED:
                raise LifecycleContractError("a new workflow must transition to received without an expected version")
        elif self.expected_version is None:
            raise LifecycleContractError("an existing workflow transition requires an expected version")
        if self.to_status not in _ALLOWED_TRANSITIONS.get(self.from_status, frozenset()):
            source = self.from_status.value if self.from_status else "none"
            raise LifecycleContractError(f"workflow transition {source} -> {self.to_status.value} is not allowed")
        try:
            parsed = datetime.fromisoformat(self.occurred_at)
        except ValueError as exc:
            raise LifecycleContractError("occurred_at must be an ISO-8601 timestamp") from exc
        if parsed.tzinfo is None:
            raise LifecycleContractError("occurred_at must include an explicit timezone")
        try:
            json.dumps(self.attributes, sort_keys=True, separators=(",", ":"))
        except (TypeError, ValueError) as exc:
            raise LifecycleContractError("attributes must be canonical JSON data") from exc

    def canonical_payload(self) -> dict[str, object]:
        self.validate()
        return {
            "schema_version": self.schema_version,
            "event_id": self.event_id,
            "idempotency_key": self.idempotency_key,
            "workflow_id": self.workflow_id,
            "tenant_id": self.tenant_id,
            "service_id": self.service_id,
            "environment": self.environment,
            "kind": self.kind,
            "correlation_id": self.correlation_id,
            "causation_id": self.causation_id,
            "actor": self.actor,
            "action": self.action,
            "from_status": self.from_status.value if self.from_status else None,
            "to_status": self.to_status.value,
            "expected_version": self.expected_version,
            "plan_hash": self.plan_hash,
            "consequential": self.consequential,
            "attributes": dict(self.attributes),
            "occurred_at": self.occurred_at,
        }

    @property
    def fingerprint(self) -> str:
        canonical = json.dumps(self.canonical_payload(), sort_keys=True, separators=(",", ":"))
        return "sha256:" + hashlib.sha256(canonical.encode()).hexdigest()

    def apply_to(self, current: WorkflowRecord | None) -> WorkflowRecord:
        """Create or advance the record after the storage adapter has read it."""
        self.validate()
        if current is None:
            if self.from_status is not None:
                raise LifecycleContractError("workflow does not exist for a non-creation transition")
            return WorkflowRecord(
                workflow_id=self.workflow_id,
                service_id=self.service_id,
                environment=self.environment,
                kind=self.kind,
                status=self.to_status,
                correlation_id=self.correlation_id,
                plan_hash=self.plan_hash,
                version=1,
                updated_at=self.occurred_at,
                tenant_id=self.tenant_id,
            )
        if self.from_status is None:
            raise LifecycleContractError("workflow already exists")
        if current.status is not self.from_status:
            raise LifecycleContractError(
                f"workflow status is {current.status.value}, expected {self.from_status.value}"
            )
        for label, actual, expected in (
            ("tenant_id", current.tenant_id, self.tenant_id),
            ("service_id", current.service_id, self.service_id),
            ("environment", current.environment, self.environment),
            ("kind", current.kind, self.kind),
            ("correlation_id", current.correlation_id, self.correlation_id),
        ):
            if actual != expected:
                raise LifecycleContractError(f"{label} cannot change during a workflow lifecycle")
        return replace(
            current,
            status=self.to_status,
            plan_hash=self.plan_hash if self.plan_hash is not None else current.plan_hash,
            updated_at=self.occurred_at,
        )


@dataclass(frozen=True)
class WorkflowTransitionResult:
    record: WorkflowRecord
    event_id: str
    idempotency_key: str
    replayed: bool = False
