import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from control_plane.workflows import ControlPlaneWorkflows
from integrations.azure_devops.deployment_failure import DeploymentFailureEvent, normalize_service_hook
from intelligence.incidents import EvidenceEvent, EvidenceKind
from product.deployment_failure_service import DeploymentFailureInvestigatorService
from state.audit import SqliteAuditLog
from state.store import SqliteStateStore


class Evidence:
    def evidence_for(self, event):
        deployed = datetime(2026, 8, 22, 10, 0, tzinfo=timezone.utc)
        return [
            EvidenceEvent(
                id=event.deployment_id,
                kind=EvidenceKind.DEPLOYMENT,
                service=event.service,
                timestamp=deployed,
                summary="deployment recorded",
                severity=1,
                source="azure-devops",
            ),
            EvidenceEvent(
                id="alert-1",
                kind=EvidenceKind.ALERT,
                service=event.service,
                timestamp=deployed + timedelta(minutes=4),
                summary="readiness failures increased",
                severity=4,
                source="azure-monitor",
            ),
        ]


class Publisher:
    def __init__(self):
        self.items = []

    def publish(self, **kwargs):
        self.items.append(kwargs)


def test_normalize_failed_ado_run():
    event = normalize_service_hook(
        {
            "resource": {
                "id": 42,
                "result": "failed",
                "project": {"name": "Platform"},
                "definition": {"id": 7, "name": "payments"},
                "environment": "prod",
                "service": "payments",
                "sourceVersion": "abc123",
            }
        }
    )
    assert event.deployment_id == "ado:Platform:7:42"
    assert event.service == "payments"
    assert event.commit_sha == "abc123"


def test_normalize_failed_ado_run_accepts_definition_id_fallback_without_coercing_payloads():
    event = normalize_service_hook(
        {
            "resource": {
                "id": "42",
                "result": "partiallySucceeded",
                "project": {"name": "Platform"},
                "definitionId": 7,
            }
        }
    )

    assert event.pipeline_id == "7"
    assert event.service == "unknown"
    assert event.commit_sha is None


@pytest.mark.parametrize(
    "payload",
    (
        {"resource": {"id": 42, "result": "failed", "project": {"name": "Platform"}}},
        {"resource": {"id": True, "result": "failed", "project": {"name": "Platform"}, "definitionId": 7}},
        {"resource": {"id": 42, "result": "failed", "project": {"name": 9}, "definitionId": 7}},
        {"resource": {"id": 42, "result": ["failed"], "project": {"name": "Platform"}, "definitionId": 7}},
    ),
)
def test_normalize_failed_ado_run_rejects_ambiguous_external_shapes(payload):
    with pytest.raises(ValueError):
        normalize_service_hook(payload)


def test_investigator_persists_analysis_and_publishes(tmp_path):
    store = SqliteStateStore(tmp_path / "state.db")
    audit = SqliteAuditLog(tmp_path / "audit.db")
    publisher = Publisher()
    service = DeploymentFailureInvestigatorService(
        evidence=Evidence(),
        workflows=ControlPlaneWorkflows(store, audit),
        publisher=publisher,
    )
    event = DeploymentFailureEvent(
        project="Platform",
        pipeline_id="7",
        run_id="42",
        deployment_id="ado:Platform:7:42",
        service="payments",
        environment="prod",
        commit_sha="abc123",
    )
    result = asyncio.run(service.investigate(event))
    assert result.workflow_id == "deployment-failure:ado:Platform:7:42"
    assert result.analysis.hypotheses
    assert result.analysis.hypotheses[0].confidence >= 0.8
    assert store.get_workflow(result.workflow_id) is not None
    assert audit.verify_chain() is True
    assert publisher.items[0]["event"].run_id == "42"
