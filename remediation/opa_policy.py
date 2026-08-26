from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from typing import Any, Protocol

from resilience.scope import parse_instant

from .catalog import Runbook
from .policy import ActionRequest, PolicyDecision, ServiceAutonomy


@dataclass(frozen=True)
class PolicyControlState:
    audit_available: bool = True
    verification_defined: bool = True


@dataclass(frozen=True)
class CertificationClaim:
    """The L4 certification a request presents, as the policy boundary sees it.

    Only the three fields a policy engine can check itself: which scope it
    certifies, which material inputs it was derived from, and when it lapses.
    """

    scope_hash: str
    inputs_hash: str
    expires_on: str

    def as_input(self) -> dict[str, str]:
        return {
            "scope_hash": str(self.scope_hash),
            "inputs_hash": str(self.inputs_hash),
            "expires_on": str(self.expires_on),
        }


#: The only downgrade a caller may declare: running an L4-policy request as a
#: supervised L3. It is the exercise path -- the promotion rule makes supervised
#: runs the *input* to certification, so they cannot require it.
SUPERVISED_DOWNGRADE = "L3"


@dataclass(frozen=True)
class AutonomyContext:
    """The autonomy level a request runs at and the certification it presents.

    ``scope_hash`` is the scope the *request* falls in. A certification whose
    ``scope_hash`` differs certifies something else, so the policy boundary can
    reject it without knowing anything about runbooks.

    ``policy_level`` is the reviewed service policy's level. It is carried
    separately from ``autonomy_level`` because a declared level is a *claim*: an
    absent or understated one must not talk the policy boundary out of asking
    for a certification.
    """

    autonomy_level: str
    scope_hash: str = ""
    now: str = ""
    certification: CertificationClaim | None = None
    policy_level: int = 0

    @property
    def is_l4(self) -> bool:
        """Whether this request must present an L4 certification.

        Mirrors ``is_l4`` in ``infra/policy/remediation-policy.rego``. A declared
        ``L4`` always counts. The single sanctioned downgrade (``L3``) does not.
        Anything else -- an absent or understated declaration, and anything that
        is not a string at all -- falls back to the reviewed policy level, so the
        field can never be used to talk the gate out of firing.

        Only a real string may carry a claim. ``None`` and a bare ``4`` are not
        declarations; coercing them with ``str()`` would be a coincidence, not a
        contract.
        """

        declared = (
            self.autonomy_level.strip().upper()
            if isinstance(self.autonomy_level, str)
            else ""
        )
        if declared == "L4":
            return True
        if declared == SUPERVISED_DOWNGRADE:
            return False
        return int(self.policy_level) >= 4

    @staticmethod
    def for_policy(policy: ServiceAutonomy) -> "AutonomyContext":
        """The honest fallback when a caller evaluates policy without a context."""

        return AutonomyContext(
            autonomy_level=f"L{int(policy.level)}",
            now=datetime.now(timezone.utc).isoformat(),
            policy_level=int(policy.level),
        )


def certification_denial(autonomy: AutonomyContext) -> str | None:
    """Deny an L4 request whose certification is absent, stale or for another scope.

    This mirrors the ``l4_certification`` rules in
    ``infra/policy/remediation-policy.rego`` so the offline reference evaluator
    and the authoritative bundle agree. It is *not* the executor's gate: the
    executor additionally checks the material-inputs hash against the inputs it
    can see, which a policy engine cannot recompute.
    """

    if not autonomy.is_l4:
        return None
    claim = autonomy.certification
    if claim is None:
        return "l4-certification: no certification record for this L4 scope"
    now = parse_instant(autonomy.now)
    if now is None:
        return "l4-certification: request carries no readable evaluation time"
    expires = parse_instant(claim.expires_on)
    if expires is None:
        return "l4-certification: certification expires_on is not a readable timestamp"
    if expires <= now:
        return f"l4-certification: certification expired on {claim.expires_on}"
    if not str(autonomy.scope_hash).strip():
        return "l4-certification: request carries no scope hash"
    if str(claim.scope_hash) != str(autonomy.scope_hash):
        return "l4-certification: record scope_hash does not match the requested scope"
    if not str(claim.inputs_hash).strip():
        return "l4-certification: certification carries no material-inputs hash"
    return None


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
        autonomy: AutonomyContext | None = None,
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
        autonomy: AutonomyContext | None = None,
    ) -> EvaluatedPolicyDecision:
        context = autonomy or AutonomyContext.for_policy(policy)
        payload: dict[str, Any] = {
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
                "autonomy_level": context.autonomy_level,
                "scope": {"scope_hash": context.scope_hash},
                "now": context.now,
                "certification": (
                    context.certification.as_input() if context.certification else None
                ),
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
        autonomy: AutonomyContext | None = None,
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
        # Mirrors the l4_certification rules in the rego bundle. A caller that
        # supplies no context is evaluated at its reviewed policy level, so an
        # L4 policy is still asked for a certification it cannot produce.
        context = autonomy or AutonomyContext.for_policy(policy)
        denial = certification_denial(replace(context, policy_level=int(policy.level)))
        if denial is not None:
            return EvaluatedPolicyDecision(False, denial, "local-reference")
        return EvaluatedPolicyDecision(True, "authorized by local reference policy", "local-reference")


def as_policy_decision(value: EvaluatedPolicyDecision) -> PolicyDecision:
    return PolicyDecision(value.allowed, f"{value.reason} [policy={value.policy_revision}]")
