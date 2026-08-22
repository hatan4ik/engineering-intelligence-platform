from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from typing import Protocol

from .catalog import Runbook
from .policy import ActionRequest, PolicyDecision, ServiceAutonomy


@dataclass(frozen=True)
class PolicyControlState:
    audit_available: bool = True
    verification_defined: bool = True


@dataclass(frozen=True)
class EvaluatedPolicyDecision:
    allowed: bool
    reason: str
    policy_revision: str


class PolicyEvaluator(Protocol):
    def evaluate(
        self,
        *,
        runbook: Runbook,
        policy: ServiceAutonomy,
        request: ActionRequest,
        approval_verified: bool,
        control: PolicyControlState,
    ) -> EvaluatedPolicyDecision: ...


class OpaPolicyClient:
    """Authoritative production policy decision adapter.

    OPA is a separate authorization boundary. Network/parse failures fail closed;
    callers never fall back to model output or silently permit the mutation.
    """

    def __init__(self, endpoint: str, *, timeout_seconds: float = 3.0) -> None:
        self.endpoint = endpoint.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def evaluate(
        self,
        *,
        runbook: Runbook,
        policy: ServiceAutonomy,
        request: ActionRequest,
        approval_verified: bool,
        control: PolicyControlState,
    ) -> EvaluatedPolicyDecision:
        payload = {
            "input": {
                "runbook": {
                    **asdict(runbook),
                    "required_level": int(runbook.required_level),
                },
                "policy": {
                    **asdict(policy),
                    "level": int(policy.level),
                },
                "request": {
                    **asdict(request),
                    "approval_verified": approval_verified,
                },
                "control": asdict(control),
            }
        }
        req = urllib.request.Request(
            self.endpoint + "/v1/data/engineering_intelligence/remediation/decision",
            method="POST",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as response:
                body = json.load(response)
        except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
            return EvaluatedPolicyDecision(False, f"OPA unavailable or invalid: {type(exc).__name__}", "unknown")
        result = body.get("result") if isinstance(body, dict) else None
        if not isinstance(result, dict):
            return EvaluatedPolicyDecision(False, "OPA response missing decision result", "unknown")
        return EvaluatedPolicyDecision(
            bool(result.get("allowed", False)),
            str(result.get("reason", "OPA denied without reason")),
            str(result.get("policy_revision", "unknown")),
        )


class LocalReferenceEvaluator:
    """Offline/CI reference evaluator matching the policy contract.

    It exists for deterministic tests and disconnected demos. Production should
    set EIP_REQUIRE_OPA=true and inject OpaPolicyClient.
    """

    def evaluate(
        self,
        *,
        runbook: Runbook,
        policy: ServiceAutonomy,
        request: ActionRequest,
        approval_verified: bool,
        control: PolicyControlState,
    ) -> EvaluatedPolicyDecision:
        if not control.audit_available:
            return EvaluatedPolicyDecision(False, "audit control unavailable", "local-reference")
        if not control.verification_defined:
            return EvaluatedPolicyDecision(False, "verification control unavailable", "local-reference")
        if policy.kill_switch:
            return EvaluatedPolicyDecision(False, "service kill switch is enabled", "local-reference")
        if request.service != policy.service or request.environment != policy.environment:
            return EvaluatedPolicyDecision(False, "request is outside service/environment policy scope", "local-reference")
        if request.environment not in runbook.environments:
            return EvaluatedPolicyDecision(False, "runbook is not permitted in this environment", "local-reference")
        if request.blast_radius > runbook.max_blast_radius or request.blast_radius > policy.max_blast_radius:
            return EvaluatedPolicyDecision(False, "blast radius exceeds certified limit", "local-reference")
        if policy.level < runbook.required_level:
            return EvaluatedPolicyDecision(False, "service autonomy level is below runbook requirement", "local-reference")
        if runbook.id not in policy.certified_runbooks:
            return EvaluatedPolicyDecision(False, "runbook is not certified for this service", "local-reference")
        if int(policy.level) == 3 and not approval_verified:
            return EvaluatedPolicyDecision(False, "verified human approval is required", "local-reference")
        if int(policy.level) >= 4 and request.error_budget_remaining <= 0:
            return EvaluatedPolicyDecision(False, "error budget exhausted; autonomous mutation disabled", "local-reference")
        return EvaluatedPolicyDecision(True, "authorized by local reference policy", "local-reference")


def as_policy_decision(value: EvaluatedPolicyDecision) -> PolicyDecision:
    return PolicyDecision(value.allowed, f"{value.reason} [policy={value.policy_revision}]")
