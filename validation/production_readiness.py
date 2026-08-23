from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Mapping

from resilience.certification import CertificationReport


class ReadinessArea(StrEnum):
    INTEGRATIONS = "integrations"
    IDENTITY = "identity"
    RELIABILITY = "reliability"
    SECURITY = "security"
    OBSERVABILITY = "observability"
    DATA = "data"
    L3 = "l3-certification"


@dataclass(frozen=True)
class ReadinessEvidence:
    key: str
    area: ReadinessArea
    passed: bool
    evidence_ref: str
    note: str = ""


@dataclass(frozen=True)
class ProductionReadinessReport:
    ready: bool
    score: float
    passed: tuple[str, ...]
    missing: tuple[str, ...]
    evidence_refs: tuple[str, ...]


REQUIRED_KEYS = frozenset({
    "real-source-integration",
    "entra-production-auth",
    "private-network-path",
    "ha-state-backend",
    "backup-restore-drill",
    "audit-export",
    "security-adversarial-suite",
    "control-plane-slo",
    "production-like-soak",
    "rollback-drill",
    "kill-switch-drill",
    "independent-verification",
})


def evaluate_production_readiness(
    evidence: tuple[ReadinessEvidence, ...],
    *,
    l3_report: CertificationReport | None = None,
    soak_hours: float = 0.0,
    minimum_soak_hours: float = 168.0,
    observed_metrics: Mapping[str, float] | None = None,
) -> ProductionReadinessReport:
    """Fail-closed gate separating working reference code from earned production proof."""
    by_key = {item.key: item for item in evidence}
    missing: list[str] = []
    passed: list[str] = []
    refs: list[str] = []

    for key in sorted(REQUIRED_KEYS):
        item = by_key.get(key)
        if item is None or not item.passed or not item.evidence_ref.strip():
            missing.append(key)
            continue
        passed.append(key)
        refs.append(item.evidence_ref)

    if soak_hours < minimum_soak_hours:
        missing.append(f"soak-hours<{minimum_soak_hours:g}")
    else:
        passed.append("soak-duration")

    if l3_report is None or not l3_report.l3_eligible:
        missing.append("l3-certification-evidence")
    else:
        passed.append("l3-certification-evidence")
        refs.append(l3_report.evidence_digest)

    metrics = dict(observed_metrics or {})
    if metrics.get("control_plane_success_rate", 0.0) < 0.99:
        missing.append("control-plane-success-rate>=0.99")
    else:
        passed.append("control-plane-success-rate")
    if metrics.get("audit_write_success_rate", 0.0) < 1.0:
        missing.append("audit-write-success-rate=1.0")
    else:
        passed.append("audit-write-success-rate")

    total = len(passed) + len(missing)
    score = 0.0 if total == 0 else round(len(passed) / total, 4)
    return ProductionReadinessReport(
        ready=not missing,
        score=score,
        passed=tuple(sorted(set(passed))),
        missing=tuple(sorted(set(missing))),
        evidence_refs=tuple(sorted(set(refs))),
    )
