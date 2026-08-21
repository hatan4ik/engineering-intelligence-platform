from __future__ import annotations

from dataclasses import dataclass

from .graph import ServiceGraph


@dataclass(frozen=True)
class ChangeContext:
    changed_services: tuple[str, ...]
    files_changed: int
    touches_iac: bool = False
    touches_identity_or_security: bool = False
    weak_test_evidence: bool = False
    similar_failed_changes: int = 0


@dataclass(frozen=True)
class RiskFactor:
    name: str
    points: int
    evidence: str


@dataclass(frozen=True)
class RiskAssessment:
    score: int
    band: str
    blast_radius: tuple[str, ...]
    factors: tuple[RiskFactor, ...]


def assess_change(graph: ServiceGraph, ctx: ChangeContext) -> RiskAssessment:
    factors: list[RiskFactor] = []
    changed = set(ctx.changed_services)
    blast = graph.blast_radius(changed)

    if graph.max_tier(blast) == 1:
        factors.append(RiskFactor("critical-service", 20, "blast radius includes tier-1 service"))
    if len(blast) >= 5:
        factors.append(RiskFactor("wide-blast-radius", 20, f"{len(blast)} services may be impacted"))
    elif len(blast) >= 2:
        factors.append(RiskFactor("multi-service-impact", 10, f"{len(blast)} services may be impacted"))
    if ctx.files_changed >= 25:
        factors.append(RiskFactor("large-diff", 15, f"{ctx.files_changed} files changed"))
    elif ctx.files_changed >= 10:
        factors.append(RiskFactor("medium-diff", 8, f"{ctx.files_changed} files changed"))
    if ctx.touches_iac:
        factors.append(RiskFactor("infrastructure-change", 12, "IaC files changed"))
    if ctx.touches_identity_or_security:
        factors.append(RiskFactor("security-boundary-change", 20, "identity/security controls changed"))
    if ctx.weak_test_evidence:
        factors.append(RiskFactor("weak-test-evidence", 10, "test evidence is missing or weak"))
    if ctx.similar_failed_changes:
        pts = min(20, 8 * ctx.similar_failed_changes)
        factors.append(RiskFactor("historical-regression", pts, f"{ctx.similar_failed_changes} similar failed changes"))

    score = min(100, sum(f.points for f in factors))
    band = "low" if score < 25 else "moderate" if score < 50 else "high" if score < 75 else "critical"
    return RiskAssessment(score, band, tuple(sorted(blast)), tuple(factors))
