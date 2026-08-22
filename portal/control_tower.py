from __future__ import annotations

from finops.live_control_tower import ControlTowerSnapshot


def to_dict(snapshot: ControlTowerSnapshot) -> dict[str, object]:
    return {
        "engineering": dict(snapshot.engineering),
        "remediation": dict(snapshot.remediation),
        "cost_by_service": dict(snapshot.cost_by_service),
        "cost_by_agent": dict(snapshot.cost_by_agent),
        "cost_anomalies": list(snapshot.cost_anomalies),
    }
