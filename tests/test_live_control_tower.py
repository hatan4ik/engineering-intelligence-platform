from finops.live_control_tower import OutcomeEvent, build_control_tower, detect_cost_anomalies
from portal.control_tower import to_dict
from telemetry.events import OperationEvent


def operation(correlation, *, service, agent, outcome="success", cost=0.0, phase="retrieve", latency=20.0):
    return OperationEvent(
        correlation_id=correlation,
        operation=phase,
        component="test",
        outcome=outcome,
        latency_ms=latency,
        service=service,
        agent=agent,
        model_cost_usd=cost,
    )


def test_control_tower_uses_measured_cost_outcomes_and_remediation_slo():
    operations = [
        operation("q1", service="payments", agent="rag", cost=0.10),
        operation("q2", service="orders", agent="rag", cost=0.02),
        operation("r1", service="payments", agent="control-plane", outcome="succeeded", phase="remediation.terminal", latency=120.0),
        operation("r2", service="payments", agent="control-plane", outcome="rolled_back", phase="remediation.terminal", latency=300.0),
    ]
    outcomes = [
        OutcomeEvent("deployment", "payments"),
        OutcomeEvent("deployment", "payments"),
        OutcomeEvent("deployment-failure", "payments"),
        OutcomeEvent("incident", "payments", duration_minutes=20, engineer_minutes_saved=30),
        OutcomeEvent("incident", "payments", duration_minutes=10, repeated=True, engineer_minutes_saved=30),
        OutcomeEvent("recommendation", "payments", prevented=True),
    ]
    snapshot = build_control_tower(
        operations=operations,
        outcomes=outcomes,
        loaded_labor_rate_usd=100.0,
    )
    assert snapshot.engineering["change_failure_rate"] == 0.5
    assert snapshot.engineering["mttr_minutes"] == 15.0
    assert snapshot.engineering["labor_value_usd"] == 100.0
    assert snapshot.engineering["platform_cost_usd"] == 0.12
    assert snapshot.remediation["success_rate"] == 0.5
    assert snapshot.remediation["rollback_rate"] == 0.5
    assert snapshot.remediation["p95_latency_ms"] == 300.0
    rendered = to_dict(snapshot)
    assert rendered["cost_by_service"]["payments"] == 0.1


def test_cost_anomaly_is_relative_and_has_minimum_floor():
    operations = [
        operation("1", service="a", agent="rag", cost=0.01),
        operation("2", service="b", agent="rag", cost=0.01),
        operation("3", service="c", agent="rag", cost=0.20),
    ]
    assert detect_cost_anomalies(operations) == ("c",)
