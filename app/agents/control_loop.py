from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Phase(str, Enum):
    DETECT = "detect"
    DIAGNOSE = "diagnose"
    PLAN = "plan"
    POLICY = "policy"
    APPROVE = "approve"
    EXECUTE = "execute"
    VERIFY = "verify"
    COMPLETE = "complete"
    ESCALATE = "escalate"


@dataclass
class Incident:
    signal: str
    environment: str
    service: str
    blast_radius: str = "low"
    reversible: bool = True
    runbook: str | None = None
    history: list[Phase] = field(default_factory=list)


class ControlLoop:
    """Deterministic orchestration boundary around AI-assisted diagnosis/planning.

    AI may enrich diagnosis and propose a runbook. Mutation is allowed only when
    explicit policy conditions are satisfied.
    """

    allowed_runbooks = {"restart-deployment", "rollback-deployment", "scale-out"}

    def advance(self, incident: Incident, approved: bool = False, verified: bool = False) -> Phase:
        current = incident.history[-1] if incident.history else Phase.DETECT
        if not incident.history:
            incident.history.append(Phase.DETECT)
            return Phase.DETECT
        transitions = {
            Phase.DETECT: Phase.DIAGNOSE,
            Phase.DIAGNOSE: Phase.PLAN,
            Phase.PLAN: Phase.POLICY,
        }
        if current in transitions:
            nxt = transitions[current]
        elif current == Phase.POLICY:
            safe = incident.reversible and incident.blast_radius == "low" and incident.runbook in self.allowed_runbooks
            nxt = Phase.APPROVE if safe and incident.environment == "prod" else Phase.EXECUTE if safe else Phase.ESCALATE
        elif current == Phase.APPROVE:
            nxt = Phase.EXECUTE if approved else Phase.ESCALATE
        elif current == Phase.EXECUTE:
            nxt = Phase.VERIFY
        elif current == Phase.VERIFY:
            nxt = Phase.COMPLETE if verified else Phase.ESCALATE
        else:
            nxt = current
        incident.history.append(nxt)
        return nxt
