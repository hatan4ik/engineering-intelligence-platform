from datetime import datetime, timezone

from control_plane.workflows import ControlPlaneWorkflows
from intelligence.deployment_failures import investigate_deployment_failure
from intelligence.drift import ResourceSnapshot, detect_drift
from intelligence.incidents import EvidenceEvent, EvidenceKind
from state.audit import SqliteAuditLog
from state.models import WorkflowStatus
from state.store import SqliteStateStore


def test_drift_detector_records_evidence_and_workflow(tmp_path):
    snapshot = ResourceSnapshot(
        resource_id="deployment/payments",
        service="payments",
        environment="prod",
        desired={"image": "payments:v2", "replicas": 3},
        observed={"image": "payments:v1", "replicas": 2},
        source="aks+git",
    )
    findings = detect_drift(snapshot)
    assert {f.field for f in findings} == {"image", "replicas"}
    assert all(f.severity == 4 for f in findings)

    store = SqliteStateStore(tmp_path / "state.db")
    audit = SqliteAuditLog(tmp_path / "audit.db")
    workflow = ControlPlaneWorkflows(store, audit).start_drift_review(
        resource_id=snapshot.resource_id,
        service_id=snapshot.service,
        environment=snapshot.environment,
        findings=findings,
    )
    assert workflow.status is WorkflowStatus.PLANNED
    assert workflow.plan_hash.startswith("sha256:")
    assert audit.verify_chain()


def test_no_drift_closes_review_without_mutation(tmp_path):
    snapshot = ResourceSnapshot(
        resource_id="deployment/catalog",
        service="catalog",
        environment="prod",
        desired={"image": "catalog:v4", "replicas": 3},
        observed={"image": "catalog:v4", "replicas": 3},
        source="aks+git",
    )
    store = SqliteStateStore(tmp_path / "state.db")
    audit = SqliteAuditLog(tmp_path / "audit.db")
    workflow = ControlPlaneWorkflows(store, audit).start_drift_review(
        resource_id=snapshot.resource_id,
        service_id=snapshot.service,
        environment=snapshot.environment,
        findings=detect_drift(snapshot),
    )
    assert workflow.status is WorkflowStatus.SUCCEEDED
    assert audit.verify_chain()


def test_deployment_failure_investigator_becomes_durable_workflow(tmp_path):
    events = [
        EvidenceEvent(
            id="deploy-77",
            kind=EvidenceKind.DEPLOYMENT,
            service="payments",
            timestamp=datetime(2026, 8, 22, 0, 0, tzinfo=timezone.utc),
            summary="release v77",
            source="azure-devops",
        ),
        EvidenceEvent(
            id="readiness-1",
            kind=EvidenceKind.K8S_EVENT,
            service="payments",
            timestamp=datetime(2026, 8, 22, 0, 3, tzinfo=timezone.utc),
            summary="readiness probe failed after rollout",
            source="aks",
            severity=4,
        ),
    ]
    analysis = investigate_deployment_failure(events, deployment_id="deploy-77", service="payments")
    assert analysis.hypotheses[0].confidence > 0.8

    store = SqliteStateStore(tmp_path / "state.db")
    audit = SqliteAuditLog(tmp_path / "audit.db")
    workflow = ControlPlaneWorkflows(store, audit).start_deployment_failure(
        environment="prod",
        analysis=analysis,
    )
    assert workflow.kind == "deployment-failure-investigation"
    assert workflow.status is WorkflowStatus.PLANNED
    assert audit.verify_chain()
