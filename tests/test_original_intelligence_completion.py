import asyncio

from datetime import datetime, timedelta, timezone

from control_plane.workflows import ControlPlaneWorkflows
from intelligence.architecture_guard import ArchitectureRule, evaluate_architecture
from intelligence.drift import ResourceSnapshot
from intelligence.knowledge_decay import KnowledgeRecord, detect_knowledge_decay
from intelligence.predictive_risk import HistoricalChange, predict_failure_probability
from product.drift_service import DriftDetectorService
from state.audit import SqliteAuditLog
from state.store import SqliteStateStore


class DriftProvider:
    def desired(self, *, service, environment):
        return [ResourceSnapshot(
            resource_id="deploy/payments",
            service=service,
            environment=environment,
            desired={"image": "payments:v2", "replicas": 3},
            observed={"image": "payments:v1", "replicas": 3},
            source="git:main",
        )]


class Publisher:
    def __init__(self): self.items = []
    def publish(self, **kwargs): self.items.append(kwargs)


def test_drift_e2e_persists_and_audits(tmp_path):
    pub = Publisher()
    store = SqliteStateStore(tmp_path / "state.db")
    audit = SqliteAuditLog(tmp_path / "audit.db")
    result = asyncio.run(
        DriftDetectorService(
            provider=DriftProvider(),
            workflows=ControlPlaneWorkflows(store, audit),
            publisher=pub,
        ).run(service="payments", environment="prod")
    )
    assert result.findings[0].field == "image"
    assert result.findings[0].severity == 4
    assert store.get_workflow(result.workflow_ids[0]) is not None
    assert audit.verify_chain() is True
    assert pub.items


def test_architecture_guard_is_rule_based():
    rules = (ArchitectureRule("no-public-ai", "infra/*.tf", ("public_network_access_enabled = true",), "AI endpoints must remain private", 5),)
    violations = evaluate_architecture("infra/main.tf", "public_network_access_enabled = true", rules)
    assert violations[0].rule_id == "no-public-ai"
    assert violations[0].severity == 5


def test_knowledge_decay_detects_stale_ownerless_and_conflict():
    now = datetime(2026, 8, 22, tzinfo=timezone.utc)
    records = [
        KnowledgeRecord("adr-1", "adr", "Auth Architecture", "v1", now - timedelta(days=400), None),
        KnowledgeRecord("adr-2", "adr", "Auth Architecture", "v2", now - timedelta(days=10), "platform"),
    ]
    kinds = {f.kind for f in detect_knowledge_decay(records, now=now)}
    assert {"stale", "missing-owner", "conflict"}.issubset(kinds)


def test_predictive_risk_uses_service_history():
    history = [
        HistoricalChange("payments", 70, True, True, True, 5),
        HistoricalChange("payments", 65, True, True, False, 4),
        HistoricalChange("payments", 20, False, False, False, 1),
    ]
    result = predict_failure_probability(service="payments", current_risk_score=72, touched_iac=True, touched_security=True, blast_radius=5, history=history)
    assert result.probability > 0.5
    assert result.confidence > 0.5
    assert result.evidence
