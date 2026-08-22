from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Mapping

from feedback.store import FeedbackMetrics
from finops.live_control_tower import ControlTowerSnapshot


class MetricBasis(StrEnum):
    MEASURED = "measured"
    DERIVED = "derived"
    MODELED = "modeled"


@dataclass(frozen=True)
class MetricValue:
    name: str
    value: float
    unit: str
    basis: MetricBasis
    source: str
    formula: str | None = None


@dataclass(frozen=True)
class PortfolioIntelligenceView:
    metrics: tuple[MetricValue, ...]
    cost_by_service: Mapping[str, float]
    cost_by_agent: Mapping[str, float]
    cost_anomalies: tuple[str, ...]
    feedback: FeedbackMetrics

    def metric(self, name: str) -> MetricValue:
        for metric in self.metrics:
            if metric.name == name:
                return metric
        raise KeyError(name)


def build_portfolio_view(
    snapshot: ControlTowerSnapshot,
    *,
    feedback: FeedbackMetrics,
) -> PortfolioIntelligenceView:
    eng = snapshot.engineering
    rem = snapshot.remediation
    metrics: list[MetricValue] = []

    # Engineering rates are deterministic aggregates over observed outcome events.
    engineering_derived = (
        ("change_failure_rate", "ratio", "failed deployments / deployments"),
        ("incident_recurrence_rate", "ratio", "repeated incidents / incidents"),
        ("mttr_minutes", "minutes", "mean incident restoration duration"),
    )
    for name, unit, formula in engineering_derived:
        if name in eng:
            metrics.append(MetricValue(
                name, float(eng[name]), unit, MetricBasis.DERIVED,
                "outcome-events", formula,
            ))

    # These values come from directly attributed outcome or operation events.
    for name, unit in (("prevented_incidents", "count"), ("platform_cost_usd", "usd")):
        if name in eng:
            metrics.append(MetricValue(
                name, float(eng[name]), unit, MetricBasis.MEASURED,
                "outcome-events" if name == "prevented_incidents" else "operation-cost-events",
            ))

    for name, unit in (
        ("success_rate", "ratio"),
        ("rollback_rate", "ratio"),
        ("p95_latency_ms", "milliseconds"),
        ("denied", "count"),
        ("failed", "count"),
    ):
        if name in rem:
            metrics.append(MetricValue(
                f"remediation_{name}",
                float(rem[name]),
                unit,
                MetricBasis.DERIVED,
                "control-plane-telemetry",
                "deterministic aggregation over OperationEvent telemetry",
            ))

    # Financial value uses configured labor-rate assumptions and must never be
    # rendered as a directly measured engineering result.
    for candidate in ("labor_value_usd", "net_value_usd", "roi_multiple"):
        if candidate in eng:
            metrics.append(MetricValue(
                candidate,
                float(eng[candidate]),
                "ratio" if candidate == "roi_multiple" else "usd",
                MetricBasis.MODELED,
                "benefit-model",
                "observed engineering outcomes combined with configured loaded labor rate",
            ))

    if feedback.acceptance_rate is not None:
        metrics.append(MetricValue(
            "recommendation_acceptance_rate",
            feedback.acceptance_rate,
            "ratio",
            MetricBasis.DERIVED,
            "feedback-events",
            "accepted / (accepted + rejected)",
        ))
    if feedback.precision is not None:
        metrics.append(MetricValue(
            "intelligence_precision",
            feedback.precision,
            "ratio",
            MetricBasis.DERIVED,
            "feedback-events",
            "correct / (correct + incorrect)",
        ))

    return PortfolioIntelligenceView(
        metrics=tuple(sorted(metrics, key=lambda m: m.name)),
        cost_by_service=snapshot.cost_by_service,
        cost_by_agent=snapshot.cost_by_agent,
        cost_anomalies=snapshot.cost_anomalies,
        feedback=feedback,
    )


def to_dict(view: PortfolioIntelligenceView) -> dict[str, object]:
    return {
        "metrics": [
            {
                "name": metric.name,
                "value": metric.value,
                "unit": metric.unit,
                "basis": metric.basis.value,
                "source": metric.source,
                "formula": metric.formula,
            }
            for metric in view.metrics
        ],
        "cost_by_service": dict(view.cost_by_service),
        "cost_by_agent": dict(view.cost_by_agent),
        "cost_anomalies": list(view.cost_anomalies),
        "feedback": {
            "total": view.feedback.total,
            "accepted": view.feedback.accepted,
            "rejected": view.feedback.rejected,
            "reverted": view.feedback.reverted,
            "correct": view.feedback.correct,
            "incorrect": view.feedback.incorrect,
            "acceptance_rate": view.feedback.acceptance_rate,
            "precision": view.feedback.precision,
        },
    }
