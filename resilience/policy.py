from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PlatformHealth:
    knowledge_available: bool
    observability_available: bool
    policy_available: bool
    audit_available: bool


@dataclass(frozen=True)
class AutonomyCertification:
    service: str
    environment: str
    runbook_id: str
    max_blast_radius: int
    rollback_tested: bool
    kill_switch_tested: bool
    verification_independent: bool
    security_reviewed: bool

    @property
    def l4_eligible(self) -> bool:
        return all((
            self.max_blast_radius > 0,
            self.rollback_tested,
            self.kill_switch_tested,
            self.verification_independent,
            self.security_reviewed,
        ))


def degraded_mode(health: PlatformHealth) -> str:
    if not health.policy_available or not health.audit_available:
        return "read-only"
    if not health.observability_available:
        return "recommend-only"
    if not health.knowledge_available:
        return "deterministic-runbooks-only"
    return "normal"
