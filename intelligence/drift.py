from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class ResourceSnapshot:
    resource_id: str
    service: str
    environment: str
    desired: Mapping[str, object]
    observed: Mapping[str, object]
    source: str


@dataclass(frozen=True)
class DriftFinding:
    resource_id: str
    service: str
    environment: str
    field: str
    desired: object
    observed: object
    evidence: str
    severity: int


def detect_drift(snapshot: ResourceSnapshot) -> tuple[DriftFinding, ...]:
    findings: list[DriftFinding] = []
    keys = sorted(set(snapshot.desired) | set(snapshot.observed))
    for key in keys:
        desired = snapshot.desired.get(key)
        observed = snapshot.observed.get(key)
        if desired == observed:
            continue
        severity = 4 if key in {"image", "identity", "network_policy", "replicas"} else 2
        findings.append(
            DriftFinding(
                resource_id=snapshot.resource_id,
                service=snapshot.service,
                environment=snapshot.environment,
                field=key,
                desired=desired,
                observed=observed,
                evidence=f"{snapshot.source}: desired {key}={desired!r}, observed {key}={observed!r}",
                severity=severity,
            )
        )
    return tuple(findings)
