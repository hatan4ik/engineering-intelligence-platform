from __future__ import annotations

from dataclasses import dataclass

from .catalog import AutonomyLevel, Runbook


@dataclass(frozen=True)
class ServiceAutonomy:
    service: str
    environment: str
    level: AutonomyLevel
    certified_runbooks: tuple[str, ...] = ()
    max_blast_radius: int = 0
    kill_switch: bool = False


@dataclass(frozen=True)
class ActionRequest:
    service: str
    environment: str
    runbook_id: str
    blast_radius: int
    approval_token: str | None = None
    error_budget_remaining: float = 1.0


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    reason: str


def authorize(runbook: Runbook, policy: ServiceAutonomy, request: ActionRequest) -> PolicyDecision:
    if policy.kill_switch:
        return PolicyDecision(False, "service kill switch is enabled")
    if request.service != policy.service or request.environment != policy.environment:
        return PolicyDecision(False, "request is outside service/environment policy scope")
    if request.environment not in runbook.environments:
        return PolicyDecision(False, "runbook is not permitted in this environment")
    if request.blast_radius > runbook.max_blast_radius or request.blast_radius > policy.max_blast_radius:
        return PolicyDecision(False, "blast radius exceeds certified limit")
    if policy.level < runbook.required_level:
        return PolicyDecision(False, "service autonomy level is below runbook requirement")
    if runbook.id not in policy.certified_runbooks:
        return PolicyDecision(False, "runbook is not certified for this service")
    if policy.level == AutonomyLevel.APPROVE_AND_EXECUTE and not request.approval_token:
        return PolicyDecision(False, "human approval token is required")
    if policy.level >= AutonomyLevel.BOUNDED_AUTONOMOUS and request.error_budget_remaining <= 0:
        return PolicyDecision(False, "error budget exhausted; autonomous mutation disabled")
    return PolicyDecision(True, "authorized by deterministic autonomy policy")
