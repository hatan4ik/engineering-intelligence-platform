from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable

from portal.portfolio_view import MetricBasis, PortfolioIntelligenceView


@dataclass(frozen=True)
class MetricPoint:
    metric: str
    value: float
    observed_at: str
    basis: MetricBasis
    source: str


@dataclass(frozen=True)
class MetricTrend:
    metric: str
    points: tuple[MetricPoint, ...]
    delta: float | None
    direction: str


def capture_points(
    view: PortfolioIntelligenceView,
    *,
    observed_at: str | None = None,
) -> tuple[MetricPoint, ...]:
    timestamp = observed_at or datetime.now(timezone.utc).isoformat()
    return tuple(
        MetricPoint(
            metric=item.name,
            value=item.value,
            observed_at=timestamp,
            basis=item.basis,
            source=item.source,
        )
        for item in view.metrics
    )


def build_trend(points: Iterable[MetricPoint], *, metric: str) -> MetricTrend:
    selected = tuple(sorted((p for p in points if p.metric == metric), key=lambda p: p.observed_at))
    if not selected:
        return MetricTrend(metric, (), None, "insufficient-data")
    if len(selected) == 1:
        return MetricTrend(metric, selected, None, "insufficient-data")
    delta = selected[-1].value - selected[0].value
    if abs(delta) < 1e-12:
        direction = "flat"
    elif delta > 0:
        direction = "up"
    else:
        direction = "down"
    return MetricTrend(metric, selected, round(delta, 6), direction)


def trend_is_improvement(trend: MetricTrend) -> bool | None:
    if trend.delta is None:
        return None
    lower_is_better = {
        "change_failure_rate",
        "incident_recurrence_rate",
        "mttr_minutes",
        "platform_cost_usd",
        "remediation_rollback_rate",
        "remediation_failed",
        "remediation_p95_latency_ms",
    }
    higher_is_better = {
        "recommendation_acceptance_rate",
        "intelligence_precision",
        "remediation_success_rate",
        "net_value_usd",
        "roi_multiple",
        "prevented_incidents",
    }
    if trend.metric in lower_is_better:
        return trend.delta <= 0
    if trend.metric in higher_is_better:
        return trend.delta >= 0
    return None


def serialize_trend(trend: MetricTrend) -> dict[str, object]:
    return {
        "metric": trend.metric,
        "delta": trend.delta,
        "direction": trend.direction,
        "improved": trend_is_improvement(trend),
        "points": [
            {
                "value": point.value,
                "observed_at": point.observed_at,
                "basis": point.basis.value,
                "source": point.source,
            }
            for point in trend.points
        ],
    }
