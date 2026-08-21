from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ServiceView:
    service: str
    owner: str | None
    tier: str
    dependencies: tuple[str, ...]
    slo_target: float | None
    slo_current: float | None
    active_incidents: int
    change_risk_score: int | None
    pending_approvals: int
    last_remediation: str | None = None


def to_dict(view: ServiceView) -> dict[str, object]:
    return {
        "service": view.service,
        "owner": view.owner,
        "tier": view.tier,
        "dependencies": list(view.dependencies),
        "slo": {"target": view.slo_target, "current": view.slo_current},
        "active_incidents": view.active_incidents,
        "change_risk_score": view.change_risk_score,
        "pending_approvals": view.pending_approvals,
        "last_remediation": view.last_remediation,
    }
