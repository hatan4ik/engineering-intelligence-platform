import asyncio

from datetime import datetime, timezone

from control_plane.workflows import ControlPlaneWorkflows
from intelligence.incidents import EvidenceEvent, EvidenceKind, analyze_incident
from state.audit import SqliteAuditLog
from state.store import SqliteStateStore


def test_incident_analysis_becomes_durable_audited_workflow(tmp_path):
    events = [
        EvidenceEvent(
            id="deploy-1",
            kind=EvidenceKind.DEPLOYMENT,
            service="payments",
            timestamp=datetime(2026, 8, 22, 0, 0, tzinfo=timezone.utc),
            summary="deployment abc123",
            source="azure-devops",
        ),
        EvidenceEvent(
            id="alert-1",
            kind=EvidenceKind.ALERT,
            service="payments",
            timestamp=datetime(2026, 8, 22, 0, 5, tzinfo=timezone.utc),
            summary="OOM memory pressure",
            source="azure-monitor",
            severity=4,
        ),
        EvidenceEvent(
            id="k8s-1",
            kind=EvidenceKind.K8S_EVENT,
            service="payments",
            timestamp=datetime(2026, 8, 22, 0, 6, tzinfo=timezone.utc),
            summary="OOMKilled container due to memory limit",
            source="aks",
            severity=4,
        ),
    ]
    analysis = analyze_incident(events, service="payments")
    store = SqliteStateStore(tmp_path / "state.db")
    audit = SqliteAuditLog(tmp_path / "audit.db")

    workflow = asyncio.run(
        ControlPlaneWorkflows(store, audit).start_incident(
            service_id="payments",
            environment="prod",
            incident_id="inc-123",
            analysis=analysis,
        )
    )

    assert workflow.workflow_id == "incident:inc-123"
    assert workflow.plan_hash.startswith("sha256:")
    assert store.get_workflow(workflow.workflow_id).status.value == "planned"
    assert audit.verify_chain()
