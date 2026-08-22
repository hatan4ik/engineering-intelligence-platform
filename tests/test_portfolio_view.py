from feedback.store import FeedbackEvent, FeedbackOutcome, summarize_feedback
from finops.live_control_tower import ControlTowerSnapshot
from portal.portfolio_view import MetricBasis, build_portfolio_view, to_dict


def snapshot():
    return ControlTowerSnapshot(
        engineering={
            "change_failure_rate": 0.12,
            "incident_recurrence_rate": 0.08,
            "mttr_minutes": 22.5,
            "labor_value_usd": 12000.0,
            "platform_cost_usd": 2000.0,
            "net_value_usd": 10000.0,
            "roi_multiple": 5.0,
            "prevented_incidents": 3.0,
        },
        remediation={
            "total": 10.0,
            "success_rate": 0.9,
            "rollback_rate": 0.1,
            "denied": 2.0,
            "failed": 0.0,
            "p95_latency_ms": 850.0,
        },
        cost_by_service={"payments": 1.25},
        cost_by_agent={"pr-guardian": 0.25},
        cost_anomalies=("payments",),
    )


def test_portfolio_view_separates_observed_derived_and_modeled_metrics():
    feedback = summarize_feedback((
        FeedbackEvent("1", "pr-guardian", "pr:1", FeedbackOutcome.ACCEPTED),
        FeedbackEvent("2", "pr-guardian", "pr:2", FeedbackOutcome.REJECTED),
        FeedbackEvent("3", "incident", "inc:1", FeedbackOutcome.CORRECT),
    ))
    view = build_portfolio_view(snapshot(), feedback=feedback)

    assert view.metric("platform_cost_usd").basis is MetricBasis.MEASURED
    assert view.metric("change_failure_rate").basis is MetricBasis.DERIVED
    assert view.metric("remediation_success_rate").basis is MetricBasis.DERIVED
    assert view.metric("net_value_usd").basis is MetricBasis.MODELED
    assert view.metric("roi_multiple").basis is MetricBasis.MODELED
    assert view.metric("recommendation_acceptance_rate").value == 0.5
    assert view.metric("intelligence_precision").value == 1.0


def test_portfolio_json_preserves_lineage_for_board_consumers():
    view = build_portfolio_view(snapshot(), feedback=summarize_feedback(()))
    payload = to_dict(view)
    metrics = {item["name"]: item for item in payload["metrics"]}
    assert metrics["net_value_usd"]["basis"] == "modeled"
    assert metrics["platform_cost_usd"]["basis"] == "measured"
    assert metrics["change_failure_rate"]["source"] == "outcome-events"
    assert payload["cost_anomalies"] == ["payments"]
