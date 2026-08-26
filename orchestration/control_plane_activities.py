"""Fail-closed Temporal activity boundary for authoritative lifecycle events.

This module is deliberately not registered by the evidence worker.  It is the
next product-control-plane slice: once a separately configured worker is
introduced, every consequential workflow transition must pass through this
state-and-audit boundary before the workflow can advance.
"""
from __future__ import annotations

from dataclasses import dataclass

from temporalio import activity

from state.audit import AuditLog
from state.lifecycle import WorkflowLifecycleEvent
from state.models import AuditEvent, WorkflowRecord
from state.store import StateStore


class AuditExportFailure(RuntimeError):
    """A lifecycle state change cannot be acknowledged without its audit export."""


@dataclass(frozen=True)
class WorkflowLifecycleActivityResult:
    workflow_id: str
    workflow_version: int
    status: str
    event_id: str
    idempotency_key: str
    state_replayed: bool
    audit_event_hash: str


class ControlPlaneActivityBridge:
    """Persist one lifecycle event and its audit record with retry-safe semantics.

    State is committed first together with an idempotency receipt. If audit
    export then fails, the activity raises and Temporal retries it. The retry
    resolves the receipt, does not advance state a second time, and attempts
    the same deterministic audit event again. A workflow must not schedule a
    consequential next step until this activity returns successfully.
    """

    def __init__(self, state: StateStore, audit: AuditLog) -> None:
        self.state = state
        self.audit = audit

    @activity.defn(name="eip.persist-workflow-lifecycle.v1")
    def persist_workflow_lifecycle(
        self, event: WorkflowLifecycleEvent
    ) -> WorkflowLifecycleActivityResult:
        transition = self.state.apply_workflow_event(event)
        audit_event = _audit_event(event, transition.record)
        try:
            exported = self.audit.append(audit_event)
        except Exception as exc:
            raise AuditExportFailure(
                "workflow lifecycle state was retained, but immutable audit export did not complete"
            ) from exc
        if not exported.event_hash:
            raise AuditExportFailure("audit exporter returned an event without a verifiable hash")
        return WorkflowLifecycleActivityResult(
            workflow_id=transition.record.workflow_id,
            workflow_version=transition.record.version,
            status=transition.record.status.value,
            event_id=event.event_id,
            idempotency_key=event.idempotency_key,
            state_replayed=transition.replayed,
            audit_event_hash=exported.event_hash,
        )


def _audit_event(event: WorkflowLifecycleEvent, record: WorkflowRecord) -> AuditEvent:
    return AuditEvent(
        event_id=f"workflow-lifecycle:{event.event_id}",
        correlation_id=event.correlation_id,
        actor=event.actor,
        action=event.action,
        resource=event.workflow_id,
        occurred_at=event.occurred_at,
        payload={
            "schema_version": event.schema_version,
            "event_id": event.event_id,
            "idempotency_key": event.idempotency_key,
            "causation_id": event.causation_id,
            "tenant_id": event.tenant_id,
            "service_id": event.service_id,
            "environment": event.environment,
            "kind": event.kind,
            "from_status": event.from_status.value if event.from_status else None,
            "to_status": event.to_status.value,
            "expected_version": event.expected_version,
            "resulting_version": record.version,
            "plan_hash": record.plan_hash,
            "consequential": event.consequential,
            "event_fingerprint": event.fingerprint,
            "attributes": dict(event.attributes),
        },
    )
