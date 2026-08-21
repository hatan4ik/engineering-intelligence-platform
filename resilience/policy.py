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
    error_budget_enforced: bool = False
    policy_fail_closed_tested: bool = False
    audit_fail_closed_tested: bool = False
    successful_exercises: int = 0
    minimum_exercises: int = 3

    @property
    def l4_eligible(self) -> bool:
        return all(
            (
                self.max_blast_radius > 0,
                self.rollback_tested,
                self.kill_switch_tested,
                self.verification_independent,
                self.security_reviewed,
                self.error_budget_enforced,
                self.policy_fail_closed_tested,
                self.audit_fail_closed_tested,
                self.successful_exercises >= self.minimum_exercises,
            )
        )

    @property
    def missing_controls(self) -> tuple[str, ...]:
        missing: list[str] = []
        checks = {
            "bounded-blast-radius": self.max_blast_radius > 0,
            "rollback-tested": self.rollback_tested,
            "kill-switch-tested": self.kill_switch_tested,
            "independent-verification": self.verification_independent,
            "security-review": self.security_reviewed,
            "error-budget-enforced": self.error_budget_enforced,
            "policy-fail-closed-tested": self.policy_fail_closed_tested,
            "audit-fail-closed-tested": self.audit_fail_closed_tested,
            "minimum-exercises": self.successful_exercises >= self.minimum_exercises,
        }
        for name, passed in checks.items():
            if not passed:
                missing.append(name)
        return tuple(missing)


def degraded_mode(health: PlatformHealth) -> str:
    if not health.policy_available or not health.audit_available:
        return "read-only"
    if not health.observability_available:
        return "recommend-only"
    if not health.knowledge_available:
        return "deterministic-runbooks-only"
    return "normal"
