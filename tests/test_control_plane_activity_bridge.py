"""Deterministic recovery tests for the future Temporal state/audit bridge."""
from __future__ import annotations

import pytest

pytest.importorskip("temporalio")

from orchestration.control_plane_activities import AuditExportFailure, ControlPlaneActivityBridge
from state.audit import SqliteAuditLog
from state.lifecycle import LifecycleContractError, WorkflowLifecycleEvent
from state.models import WorkflowStatus
from state.store import SqliteStateStore, VersionConflict


def lifecycle_event(
    *,
    event_id: str,
    idempotency_key: str,
    from_status: WorkflowStatus | None,
    to_status: WorkflowStatus,
    expected_version: int | None = None,
    action: str = "record-lifecycle",
) -> WorkflowLifecycleEvent:
    return WorkflowLifecycleEvent(
        event_id=event_id,
        idempotency_key=idempotency_key,
        workflow_id="incident:payment-latency-42",
        tenant_id="contoso",
        service_id="payments",
        environment="prod",
        kind="incident-investigation",
        correlation_id="corr-payment-latency-42",
        actor="agent:incident-investigator",
        action=action,
        from_status=from_status,
        to_status=to_status,
        expected_version=expected_version,
        plan_hash="sha256:" + "a" * 64,
        causation_id="source-event:42",
        attributes={"incident_id": "payment-latency-42"},
        occurred_at="2026-08-26T12:00:00+00:00",
    )


def test_duplicate_delivery_reuses_state_receipt_and_audit_event(tmp_path):
    state = SqliteStateStore(tmp_path / "state.db")
    audit = SqliteAuditLog(tmp_path / "audit.db")
    bridge = ControlPlaneActivityBridge(state, audit)
    event = lifecycle_event(
        event_id="evt-received",
        idempotency_key="idem-received",
        from_status=None,
        to_status=WorkflowStatus.RECEIVED,
        expected_version=None,
    )

    first = bridge.persist_workflow_lifecycle(event)
    retry = bridge.persist_workflow_lifecycle(event)

    assert first.workflow_version == retry.workflow_version == 1
    assert not first.state_replayed
    assert retry.state_replayed
    assert audit.event_count() == 1
    assert audit.verify_chain()


def test_stale_transition_is_rejected_without_audit_write(tmp_path):
    state = SqliteStateStore(tmp_path / "state.db")
    audit = SqliteAuditLog(tmp_path / "audit.db")
    bridge = ControlPlaneActivityBridge(state, audit)
    bridge.persist_workflow_lifecycle(
        lifecycle_event(
            event_id="evt-received",
            idempotency_key="idem-received",
            from_status=None,
            to_status=WorkflowStatus.RECEIVED,
            expected_version=None,
        )
    )
    bridge.persist_workflow_lifecycle(
        lifecycle_event(
            event_id="evt-diagnosing",
            idempotency_key="idem-diagnosing",
            from_status=WorkflowStatus.RECEIVED,
            to_status=WorkflowStatus.DIAGNOSING,
            expected_version=1,
        )
    )

    with pytest.raises(VersionConflict, match="expected version 1, current version is 2"):
        bridge.persist_workflow_lifecycle(
            lifecycle_event(
                event_id="evt-stale-plan",
                idempotency_key="idem-stale-plan",
                from_status=WorkflowStatus.RECEIVED,
                to_status=WorkflowStatus.PLANNED,
                expected_version=1,
            )
        )
    assert state.get_workflow("incident:payment-latency-42").status is WorkflowStatus.DIAGNOSING
    assert audit.event_count() == 2


def test_audit_outage_retries_without_reapplying_state_after_worker_restart(tmp_path):
    state_path = tmp_path / "state.db"
    audit_path = tmp_path / "audit.db"
    event = lifecycle_event(
        event_id="evt-received",
        idempotency_key="idem-received",
        from_status=None,
        to_status=WorkflowStatus.RECEIVED,
    )

    class FailingAudit:
        def append(self, _event):
            raise OSError("immutable audit export unavailable")

    first_worker = ControlPlaneActivityBridge(SqliteStateStore(state_path), FailingAudit())
    with pytest.raises(AuditExportFailure, match="state was retained"):
        first_worker.persist_workflow_lifecycle(event)
    assert SqliteStateStore(state_path).get_workflow(event.workflow_id).version == 1

    recovered_audit = SqliteAuditLog(audit_path)
    replacement_worker = ControlPlaneActivityBridge(SqliteStateStore(state_path), recovered_audit)
    retry = replacement_worker.persist_workflow_lifecycle(event)

    assert retry.state_replayed
    assert retry.workflow_version == 1
    assert recovered_audit.event_count() == 1
    assert recovered_audit.verify_chain()


def test_cancellation_is_explicit_and_terminal(tmp_path):
    state = SqliteStateStore(tmp_path / "state.db")
    audit = SqliteAuditLog(tmp_path / "audit.db")
    bridge = ControlPlaneActivityBridge(state, audit)
    bridge.persist_workflow_lifecycle(
        lifecycle_event(
            event_id="evt-received",
            idempotency_key="idem-received",
            from_status=None,
            to_status=WorkflowStatus.RECEIVED,
            expected_version=None,
        )
    )
    cancelled = bridge.persist_workflow_lifecycle(
        lifecycle_event(
            event_id="evt-cancelled",
            idempotency_key="idem-cancelled",
            from_status=WorkflowStatus.RECEIVED,
            to_status=WorkflowStatus.CANCELLED,
            expected_version=1,
            action="cancel-workflow",
        )
    )

    assert cancelled.status == WorkflowStatus.CANCELLED.value
    with pytest.raises(LifecycleContractError, match="not allowed"):
        bridge.persist_workflow_lifecycle(
            lifecycle_event(
                event_id="evt-resume-cancelled",
                idempotency_key="idem-resume-cancelled",
                from_status=WorkflowStatus.CANCELLED,
                to_status=WorkflowStatus.EXECUTING,
                expected_version=2,
            )
        )
