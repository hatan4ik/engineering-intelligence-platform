from __future__ import annotations

from dataclasses import dataclass
from statistics import median

from finops.attribution import from_operation
from finops.outcomes import EngineeringOutcomes, control_tower
from telemetry.control_plane import project_control_plane_slo
from telemetry.events import OperationEvent


@dataclass(frozen=True)
class OutcomeEvent:
    kind: str
    service: str
    duration_minutes: float = 0.0
    repeated: bool = False
    engineer_minutes_saved: float = 0.0
    prevented: bool = False


@dataclass(frozen=True)
class ControlTowerSnapshot:
    engineering: dict[str, float]
    remediation: dict[str, float]
    cost_by_service: dict[str, float]
    cost_by_agent: dict[str, float]
    cost_anomalies: tuple[str, ...]


def _cost_totals(events: list[OperationEvent], field: str) -> dict[str, float]:
    totals: dict[str, float] = {}
    for event in events:
        cost = from_operation(event)
        key = str(getattr(cost, field) or "unknown")
        totals[key] = totals.get(key, 0.0) + cost.total_usd
    return {key: round(value, 6) for key, value in sorted(totals.items())}


def detect_cost_anomalies(events: list[OperationEvent], *, multiplier: float = 3.0, minimum_usd: float = 0.05) -> tuple[str, ...]:
    """Flag service cost outliers against the median of non-zero service totals."""
    totals = _cost_totals(events, "service")
    nonzero = [value for value in totals.values() if value > 0]
    if not nonzero:
        return ()
    baseline = median(nonzero)
    threshold = max(minimum_usd, baseline * multiplier)
    return tuple(sorted(service for service, cost in totals.items() if cost > threshold))


def build_control_tower(
    *,
    operations: list[OperationEvent],
    outcomes: list[OutcomeEvent],
    loaded_labor_rate_usd: float,
) -> ControlTowerSnapshot:
    deployments = sum(e.kind == "deployment" for e in outcomes)
    failed_deployments = sum(e.kind == "deployment-failure" for e in outcomes)
    incidents = [e for e in outcomes if e.kind == "incident"]
    mttr_values = [max(0.0, e.duration_minutes) for e in incidents if e.duration_minutes > 0]
    engineering = EngineeringOutcomes(
        deployments=deployments,
        failed_deployments=failed_deployments,
        incidents=len(incidents),
        repeated_incidents=sum(e.repeated for e in incidents),
        mttr_minutes=(sum(mttr_values) / len(mttr_values)) if mttr_values else 0.0,
        engineer_hours_saved=sum(max(0.0, e.engineer_minutes_saved) for e in outcomes) / 60.0,
        prevented_incidents=sum(e.prevented for e in outcomes),
        platform_cost_usd=sum(max(0.0, e.total_cost_usd) for e in operations),
    )
    remediation_slo = project_control_plane_slo(operations)
    remediation = {
        "total": float(remediation_slo.total),
        "success_rate": round(remediation_slo.success_rate, 4),
        "rollback_rate": round(remediation_slo.rollback_rate, 4),
        "denied": float(remediation_slo.denied),
        "failed": float(remediation_slo.failed),
        "p95_latency_ms": round(remediation_slo.p95_latency_ms, 2),
    }
    return ControlTowerSnapshot(
        engineering=control_tower(engineering, loaded_labor_rate_usd=loaded_labor_rate_usd),
        remediation=remediation,
        cost_by_service=_cost_totals(operations, "service"),
        cost_by_agent=_cost_totals(operations, "agent"),
        cost_anomalies=detect_cost_anomalies(operations),
    )
