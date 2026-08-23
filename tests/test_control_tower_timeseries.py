from feedback.store import FeedbackMetrics
from finops.live_control_tower import ControlTowerSnapshot
from portal.portfolio_view import build_portfolio_view
from portal.timeseries import build_trend, capture_points, serialize_trend, trend_is_improvement


def view(mttr: float, cfr: float, precision: float):
    snapshot = ControlTowerSnapshot(
        engineering={
            "change_failure_rate": cfr,
            "incident_recurrence_rate": 0.2,
            "mttr_minutes": mttr,
            "labor_value_usd": 1000.0,
            "platform_cost_usd": 100.0,
            "net_value_usd": 900.0,
            "roi_multiple": 9.0,
            "prevented_incidents": 2.0,
        },
        remediation={
            "total": 10.0,
            "success_rate": 0.9,
            "rollback_rate": 0.1,
            "denied": 1.0,
            "failed": 1.0,
            "p95_latency_ms": 800.0,
        },
        cost_by_service={"payments": 100.0},
        cost_by_agent={"incident": 50.0},
        cost_anomalies=(),
    )
    feedback = FeedbackMetrics(10, 7, 3, 0, int(precision * 10), 10 - int(precision * 10))
    return build_portfolio_view(snapshot, feedback=feedback)


def test_mttr_down_is_improvement_and_lineage_is_retained():
    points = capture_points(view(50.0, 0.2, 0.7), observed_at="2026-08-01T00:00:00+00:00")
    points += capture_points(view(30.0, 0.1, 0.8), observed_at="2026-08-20T00:00:00+00:00")
    trend = build_trend(points, metric="mttr_minutes")
    assert trend.delta == -20.0
    assert trend.direction == "down"
    assert trend_is_improvement(trend) is True
    payload = serialize_trend(trend)
    assert payload["points"][0]["source"] == "outcome-events"


def test_precision_up_is_improvement():
    points = capture_points(view(50.0, 0.2, 0.6), observed_at="2026-08-01T00:00:00+00:00")
    points += capture_points(view(50.0, 0.2, 0.9), observed_at="2026-08-20T00:00:00+00:00")
    trend = build_trend(points, metric="intelligence_precision")
    assert trend.direction == "up"
    assert trend_is_improvement(trend) is True


def test_one_point_never_claims_a_trend():
    points = capture_points(view(50.0, 0.2, 0.7), observed_at="2026-08-01T00:00:00+00:00")
    trend = build_trend(points, metric="change_failure_rate")
    assert trend.direction == "insufficient-data"
    assert trend_is_improvement(trend) is None
