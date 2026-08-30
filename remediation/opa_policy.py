from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from typing import Mapping, Protocol

from resilience.scope import parse_instant
from resilience.dependencies import DependencyBoundary, DependencyLimits, DependencyUnavailable

from .catalog import Runbook
from .policy_contract import PolicyReason
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
AUTHORIZED_REASON = PolicyReason.AUTHORIZED.value


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

    @property
    def effective_level(self) -> int:
        """The level this request actually runs at.

        Mirrors ``effective_level`` in ``infra/policy/remediation-policy.rego``:
        the sanctioned downgrade (a declared ``L3`` under an L4 policy) runs as
        a supervised L3 -- and is therefore subject to the L3 approval rule --
        while every other claim resolves to the reviewed policy level.
        """

        declared = (
            self.autonomy_level.strip().upper()
            if isinstance(self.autonomy_level, str)
            else ""
        )
        if declared == SUPERVISED_DOWNGRADE and int(self.policy_level) >= 4:
            return 3
        return int(self.policy_level)

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
        return PolicyReason.CERTIFICATION_ABSENT.value
    now = parse_instant(autonomy.now)
    if now is None:
        return PolicyReason.EVALUATION_TIME_UNREADABLE.value
    expires = parse_instant(claim.expires_on)
    if expires is None:
        return PolicyReason.CERTIFICATION_EXPIRY_UNREADABLE.value
    if expires <= now:
        return PolicyReason.CERTIFICATION_EXPIRED.value
    if not str(autonomy.scope_hash).strip():
        return PolicyReason.SCOPE_MISSING.value
    if str(claim.scope_hash) != str(autonomy.scope_hash):
        return PolicyReason.SCOPE_MISMATCH.value
    if not str(claim.inputs_hash).strip():
        return PolicyReason.INPUTS_HASH_MISSING.value
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

    def __init__(
        self,
        endpoint: str,
        *,
        timeout_seconds: float = 3.0,
        dependency: DependencyBoundary | None = None,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self.endpoint = endpoint.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self._dependency = dependency or DependencyBoundary(
            "opa-remediation-policy",
            DependencyLimits(max_in_flight=16, failure_threshold=3, recovery_seconds=15),
        )

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
        return self.evaluate_input(
            opa_input(
                runbook=runbook,
                policy=policy,
                request=request,
                approval_verified=approval_verified,
                control=control,
                autonomy=autonomy,
            )
        )

    def evaluate_input(self, payload: Mapping[str, object]) -> EvaluatedPolicyDecision:
        """Evaluate an already-serialized OPA envelope for conformance probes.

        Product code calls :meth:`evaluate` with domain objects. This narrow
        method exists so malformed wire-level cases can be checked against the
        authoritative Rego bundle without pretending they are valid domain
        objects.
        """

        request_payload = dict(payload)
        req = urllib.request.Request(
            self.endpoint + "/v1/data/engineering_intelligence/remediation/decision",
            method="POST",
            data=json.dumps(request_payload).encode(),
            headers={"Content-Type": "application/json"},
        )
        def send() -> object:
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as response:
                return json.load(response)

        try:
            body = self._dependency.call(send, is_transient=_transient_opa_error)
        except (DependencyUnavailable, OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
            return EvaluatedPolicyDecision(False, f"OPA unavailable or invalid: {type(exc).__name__}", "unknown")
        result = body.get("result") if isinstance(body, dict) else None
        if not isinstance(result, dict):
            return EvaluatedPolicyDecision(False, "OPA response missing decision result", "unknown")
        return EvaluatedPolicyDecision(
            bool(result.get("allowed", False)),
            str(result.get("reason", "OPA denied without reason")),
            str(result.get("policy_revision", "unknown")),
        )


def policy_input_boundary_denial(payload: Mapping[str, object]) -> str | None:
    """Return the Rego-equivalent refusal for raw inputs invalid at the wire edge.

    Domain objects make a missing/non-numeric policy level unrepresentable. The
    explicit wire check closes the remaining conformance gap and retains Rego's
    kill-switch precedence for malformed raw requests.
    """

    policy = payload.get("policy")
    if isinstance(policy, Mapping) and policy.get("kill_switch") is True:
        return PolicyReason.KILL_SWITCH.value
    if not isinstance(policy, Mapping) or type(policy.get("level")) is not int:
        return PolicyReason.POLICY_LEVEL_MISSING.value
    return None


class LocalReferenceEvaluator:
    """Offline/CI reference evaluator matching the policy contract.

    It exists for deterministic tests and disconnected demos. Production should
    set EIP_REQUIRE_OPA=true and inject OpaPolicyClient.
    """

    def evaluate_input(self, payload: Mapping[str, object]) -> EvaluatedPolicyDecision:
        """Evaluate the raw-input checks that precede construction of domain objects."""

        denial = policy_input_boundary_denial(payload)
        if denial is None:
            raise ValueError("raw policy input is representable; use evaluate() with domain objects")
        return EvaluatedPolicyDecision(False, denial, "local-reference")

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
        # Keep the exact evaluation order in the Rego bundle. The reason is
        # part of the authorization contract: a later unsafe condition must
        # not replace the first deterministic refusal an operator receives.
        if policy.kill_switch:
            return EvaluatedPolicyDecision(False, PolicyReason.KILL_SWITCH.value, "local-reference")
        if request.service != policy.service or request.environment != policy.environment:
            return EvaluatedPolicyDecision(False, PolicyReason.OUTSIDE_SCOPE.value, "local-reference")
        if request.environment not in runbook.environments:
            return EvaluatedPolicyDecision(False, PolicyReason.RUNBOOK_ENVIRONMENT.value, "local-reference")
        if request.blast_radius > runbook.max_blast_radius or request.blast_radius > policy.max_blast_radius:
            return EvaluatedPolicyDecision(False, PolicyReason.BLAST_RADIUS.value, "local-reference")
        if policy.level < runbook.required_level:
            return EvaluatedPolicyDecision(False, PolicyReason.AUTONOMY_LEVEL.value, "local-reference")
        if runbook.id not in policy.certified_runbooks:
            return EvaluatedPolicyDecision(False, PolicyReason.RUNBOOK_CERTIFICATION.value, "local-reference")
        # A caller that supplies no context is evaluated at its reviewed policy
        # level; a supplied context cannot lower policy_level below the real one.
        context = replace(
            autonomy or AutonomyContext.for_policy(policy), policy_level=int(policy.level)
        )
        # Keyed on the *effective* level so the sanctioned L3 downgrade of an L4
        # scope is still asked for the human approval L3 means.
        if context.effective_level == 3 and not approval_verified:
            return EvaluatedPolicyDecision(False, PolicyReason.HUMAN_APPROVAL.value, "local-reference")
        if int(policy.level) >= 4 and request.error_budget_remaining <= 0:
            return EvaluatedPolicyDecision(False, PolicyReason.ERROR_BUDGET.value, "local-reference")
        # Mirrors the l4_certification rules in the rego bundle, so an L4 policy
        # is still asked for a certification it cannot produce.
        denial = certification_denial(context)
        if denial is not None:
            return EvaluatedPolicyDecision(False, denial, "local-reference")
        if not control.audit_available:
            return EvaluatedPolicyDecision(False, PolicyReason.AUDIT_UNAVAILABLE.value, "local-reference")
        if not control.verification_defined:
            return EvaluatedPolicyDecision(False, PolicyReason.VERIFICATION_UNAVAILABLE.value, "local-reference")
        return EvaluatedPolicyDecision(True, AUTHORIZED_REASON, "local-reference")


def opa_input(
    *,
    runbook: Runbook,
    policy: ServiceAutonomy,
    request: ActionRequest,
    approval_verified: bool,
    control: PolicyControlState,
    autonomy: AutonomyContext | None = None,
) -> dict[str, object]:
    """Serialize one typed policy decision to the Rego input contract.

    The conformance suite uses this same builder, so the local reference
    evaluator and OPA receive equivalent inputs rather than hand-maintained
    lookalike dictionaries.
    """

    context = autonomy or AutonomyContext.for_policy(policy)
    return {
        "input": {
            "runbook": {**asdict(runbook), "required_level": int(runbook.required_level)},
            "policy": {**asdict(policy), "level": int(policy.level)},
            "request": {**asdict(request), "approval_verified": approval_verified},
            "control": asdict(control),
            "autonomy_level": context.autonomy_level,
            "scope": {"scope_hash": context.scope_hash},
            "now": context.now,
            "certification": context.certification.as_input() if context.certification else None,
        }
    }


def as_policy_decision(value: EvaluatedPolicyDecision) -> PolicyDecision:
    return PolicyDecision(value.allowed, f"{value.reason} [policy={value.policy_revision}]")


def _transient_opa_error(error: Exception) -> bool:
    """Treat connectivity, malformed responses, throttling, and 5xx OPA failures as transient."""

    if isinstance(error, urllib.error.HTTPError):
        return error.code == 429 or error.code >= 500
    return isinstance(error, (OSError, urllib.error.URLError, json.JSONDecodeError))
