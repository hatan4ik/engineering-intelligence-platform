from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EngineeringOutcomes:
    deployments: int
    failed_deployments: int
    incidents: int
    repeated_incidents: int
    mttr_minutes: float
    engineer_hours_saved: float
    prevented_incidents: int
    platform_cost_usd: float

    @property
    def change_failure_rate(self) -> float:
        return 0.0 if self.deployments == 0 else self.failed_deployments / self.deployments

    @property
    def incident_recurrence_rate(self) -> float:
        return 0.0 if self.incidents == 0 else self.repeated_incidents / self.incidents


def control_tower(outcomes: EngineeringOutcomes, *, loaded_labor_rate_usd: float) -> dict[str, float]:
    labor_value = outcomes.engineer_hours_saved * loaded_labor_rate_usd
    net_value = labor_value - outcomes.platform_cost_usd
    roi = 0.0 if outcomes.platform_cost_usd <= 0 else net_value / outcomes.platform_cost_usd
    return {
        "change_failure_rate": round(outcomes.change_failure_rate, 4),
        "incident_recurrence_rate": round(outcomes.incident_recurrence_rate, 4),
        "mttr_minutes": round(outcomes.mttr_minutes, 2),
        "labor_value_usd": round(labor_value, 2),
        "platform_cost_usd": round(outcomes.platform_cost_usd, 2),
        "net_value_usd": round(net_value, 2),
        "roi_multiple": round(roi, 3),
        "prevented_incidents": float(outcomes.prevented_incidents),
    }
