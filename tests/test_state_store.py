from dataclasses import replace

import pytest

from state.audit import SqliteAuditLog
from state.models import AuditEvent, ServiceRecord, WorkflowRecord, WorkflowStatus
from state.store import SqliteStateStore, VersionConflict


def test_service_and_workflow_use_optimistic_concurrency(tmp_path):
    store = SqliteStateStore(tmp_path / "state.db")
    service = store.put_service(ServiceRecord("payments", "team-payments", tier=1))
    assert service.version == 1

    updated = store.put_service(replace(service, autonomy_level=2), expected_version=1)
    assert updated.version == 2
    assert store.get_service("payments").autonomy_level == 2

    with pytest.raises(VersionConflict):
        store.put_service(replace(service, autonomy_level=3), expected_version=1)

    workflow = store.put_workflow(
        WorkflowRecord(
            workflow_id="wf-1",
            service_id="payments",
            environment="prod",
            kind="incident-remediation",
            status=WorkflowStatus.RECEIVED,
            correlation_id="corr-1",
        )
    )
    planned = store.put_workflow(
        replace(workflow, status=WorkflowStatus.PLANNED, plan_hash="sha256:plan"),
        expected_version=1,
    )
    assert planned.version == 2
    assert store.get_workflow("wf-1").status is WorkflowStatus.PLANNED


def test_audit_chain_is_append_only_and_verifiable(tmp_path):
    audit = SqliteAuditLog(tmp_path / "audit.db")
    first = audit.append(AuditEvent("evt-1", "corr-1", "agent:incident", "diagnose", "payments", {"evidence": ["trace-1"]}))
    second = audit.append(AuditEvent("evt-2", "corr-1", "human:alice", "approve", "payments", {"plan_hash": "sha256:plan"}))

    assert first.previous_hash is None
    assert second.previous_hash == first.event_hash
    assert audit.verify_chain()

    # Simulate storage corruption: chain verification must fail closed.
    with audit._connect() as db:
        db.execute("UPDATE audit_events SET payload='{}' WHERE event_id='evt-1'")
    assert not audit.verify_chain()
