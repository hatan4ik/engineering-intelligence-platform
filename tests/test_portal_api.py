from fastapi.testclient import TestClient

from app.main import app
from feedback.store import summarize_feedback
from finops.live_control_tower import ControlTowerSnapshot
from portal.intelligence_view import (
    ArchitectureHealth,
    IncidentHealth,
    KnowledgeHealth,
    ServiceIntelligenceView,
)
from portal.portfolio_view import build_portfolio_view


class ServiceProvider:
    def get_service_view(self, *, service, principal):
        if service != "payments" or "engineering" not in principal.groups:
            return None
        return ServiceIntelligenceView(
            service="payments",
            owner="payments-team",
            tier=1,
            repositories=("acme/payments",),
            dependencies=("identity",),
            impacted_dependents=("checkout",),
            slo_target=0.999,
            slo_current=0.9995,
            change_risk_score=30,
            knowledge=KnowledgeHealth(),
            architecture=ArchitectureHealth(),
            incidents=IncidentHealth(),
            feedback=summarize_feedback(()),
        )


class PortfolioProvider:
    def get_portfolio_view(self, *, principal):
        assert "engineering" in principal.groups
        snapshot = ControlTowerSnapshot(
            engineering={
                "change_failure_rate": 0.1,
                "incident_recurrence_rate": 0.0,
                "mttr_minutes": 10.0,
                "labor_value_usd": 1000.0,
                "platform_cost_usd": 100.0,
                "net_value_usd": 900.0,
                "roi_multiple": 9.0,
                "prevented_incidents": 1.0,
            },
            remediation={
                "success_rate": 1.0, "rollback_rate": 0.0,
                "p95_latency_ms": 100.0, "denied": 0.0, "failed": 0.0,
            },
            cost_by_service={"payments": 0.1},
            cost_by_agent={"pr-guardian": 0.1},
            cost_anomalies=(),
        )
        return build_portfolio_view(snapshot, feedback=summarize_feedback(()))


def _clear_state():
    for name in ("service_intelligence_provider", "portfolio_intelligence_provider"):
        if hasattr(app.state, name):
            delattr(app.state, name)


def test_service_portal_returns_authorized_view(monkeypatch):
    monkeypatch.setenv("EIP_REQUIRE_AUTH", "false")
    _clear_state()
    app.state.service_intelligence_provider = ServiceProvider()
    response = TestClient(app).get(
        "/v1/portal/services/payments",
        headers={"x-eip-groups": "engineering", "x-eip-user": "developer"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["service"] == "payments"
    assert payload["viewer"] == {"subject": "developer", "group_count": 1}
    _clear_state()


def test_service_portal_hides_missing_or_unauthorized_service(monkeypatch):
    monkeypatch.setenv("EIP_REQUIRE_AUTH", "false")
    _clear_state()
    app.state.service_intelligence_provider = ServiceProvider()
    response = TestClient(app).get(
        "/v1/portal/services/payments",
        headers={"x-eip-groups": "other"},
    )
    assert response.status_code == 404
    _clear_state()


def test_portfolio_portal_preserves_metric_lineage(monkeypatch):
    monkeypatch.setenv("EIP_REQUIRE_AUTH", "false")
    _clear_state()
    app.state.portfolio_intelligence_provider = PortfolioProvider()
    response = TestClient(app).get(
        "/v1/portal/portfolio",
        headers={"x-eip-groups": "engineering", "x-eip-user": "vp-eng"},
    )
    assert response.status_code == 200
    metrics = {item["name"]: item for item in response.json()["metrics"]}
    assert metrics["net_value_usd"]["basis"] == "modeled"
    assert response.json()["viewer"]["subject"] == "vp-eng"
    _clear_state()


def test_portal_fails_closed_without_provider(monkeypatch):
    monkeypatch.setenv("EIP_REQUIRE_AUTH", "false")
    _clear_state()
    response = TestClient(app).get("/v1/portal/portfolio")
    assert response.status_code == 503
