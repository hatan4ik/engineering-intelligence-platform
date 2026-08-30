"""A shared, adversarial corpus for remediation-policy implementations.

The Rego bundle is the authorization boundary. The local evaluator exists for
reference/CI use and must return the same allow/deny verdict and reason for
every representable input in this corpus. Policy revisions are intentionally
different identifiers and are not compared here.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from .catalog import AutonomyLevel, Runbook, default_catalog
from .opa_policy import AutonomyContext, CertificationClaim, PolicyControlState, opa_input
from .policy_contract import PolicyReason, RegoDenyBranch, branch_requirement
from .policy import ActionRequest, ServiceAutonomy


@dataclass(frozen=True)
class PolicyConformanceCase:
    """One full evaluator invocation and its Rego-contract outcome."""

    name: str
    runbook: Runbook
    policy: ServiceAutonomy
    request: ActionRequest
    approval_verified: bool
    control: PolicyControlState
    autonomy: AutonomyContext
    allowed: bool
    reason: str
    branch: RegoDenyBranch | None


@dataclass(frozen=True)
class RawPolicyConformanceCase:
    """A malformed wire-level input that has no valid domain-object form.

    ``input`` is the object below the OPA envelope's ``input`` key.  These
    cases close the small but important gap that typed domain constructors
    intentionally make unrepresentable.
    """

    name: str
    input: dict[str, object]
    allowed: bool
    reason: str
    branch: RegoDenyBranch


def remediation_policy_conformance_cases() -> tuple[PolicyConformanceCase, ...]:
    """Return deterministic cases covering each ordered Rego decision branch."""

    catalog = default_catalog()
    l3_runbook = catalog.get("aks.rollout.undo")
    l3_policy = ServiceAutonomy(
        service="payments",
        environment="prod",
        level=AutonomyLevel.APPROVE_AND_EXECUTE,
        certified_runbooks=(l3_runbook.id,),
        max_blast_radius=5,
    )
    l3_request = ActionRequest(
        service="payments",
        environment="prod",
        runbook_id=l3_runbook.id,
        blast_radius=2,
        approval_token="verified:workflow",
        error_budget_remaining=1.0,
    )
    l3_context = AutonomyContext(
        autonomy_level="L3",
        now="2026-08-28T00:00:00+00:00",
        policy_level=int(l3_policy.level),
    )
    l4_runbook = catalog.get("aks.scale.memory")
    l4_policy = ServiceAutonomy(
        service="payments",
        environment="stage",
        level=AutonomyLevel.BOUNDED_AUTONOMOUS,
        certified_runbooks=(l4_runbook.id,),
        max_blast_radius=5,
    )
    l4_request = ActionRequest(
        service="payments",
        environment="stage",
        runbook_id=l4_runbook.id,
        blast_radius=2,
        error_budget_remaining=1.0,
    )
    valid_claim = CertificationClaim(
        scope_hash="scope-a",
        inputs_hash="inputs-a",
        expires_on="2026-09-01T00:00:00+00:00",
    )
    l4_context = AutonomyContext(
        autonomy_level="L4",
        scope_hash="scope-a",
        now="2026-08-28T00:00:00+00:00",
        certification=valid_claim,
        policy_level=int(l4_policy.level),
    )

    return (
        _case(
            "authorized-l3",
            l3_runbook,
            l3_policy,
            l3_request,
            True,
            PolicyControlState(),
            l3_context,
            True,
            PolicyReason.AUTHORIZED.value,
        ),
        _case(
            "kill-switch-precedes-all-other-failures",
            l3_runbook,
            replace(l3_policy, kill_switch=True),
            replace(l3_request, service="other", blast_radius=99),
            False,
            PolicyControlState(audit_available=False),
            l3_context,
            False,
            PolicyReason.KILL_SWITCH.value,
        ),
        _case(
            "scope-service",
            l3_runbook,
            l3_policy,
            replace(l3_request, service="other"),
            True,
            PolicyControlState(),
            l3_context,
            False,
            PolicyReason.OUTSIDE_SCOPE.value,
        ),
        _case(
            "scope-environment",
            l3_runbook,
            l3_policy,
            replace(l3_request, environment="stage"),
            True,
            PolicyControlState(),
            l3_context,
            False,
            PolicyReason.OUTSIDE_SCOPE.value,
        ),
        _case(
            "runbook-environment",
            replace(l3_runbook, environments=("stage",)),
            replace(l3_policy, environment="dev"),
            replace(l3_request, environment="dev"),
            True,
            PolicyControlState(),
            l3_context,
            False,
            PolicyReason.RUNBOOK_ENVIRONMENT.value,
        ),
        _case(
            "runbook-blast-radius",
            l3_runbook,
            replace(l3_policy, max_blast_radius=99),
            replace(l3_request, blast_radius=l3_runbook.max_blast_radius + 1),
            True,
            PolicyControlState(),
            l3_context,
            False,
            PolicyReason.BLAST_RADIUS.value,
        ),
        _case(
            "service-blast-radius",
            l3_runbook,
            l3_policy,
            replace(l3_request, blast_radius=l3_policy.max_blast_radius + 1),
            True,
            PolicyControlState(),
            l3_context,
            False,
            PolicyReason.BLAST_RADIUS.value,
        ),
        _case(
            "autonomy-level",
            l3_runbook,
            replace(l3_policy, level=AutonomyLevel.HUMAN_EXECUTE),
            l3_request,
            True,
            PolicyControlState(),
            l3_context,
            False,
            PolicyReason.AUTONOMY_LEVEL.value,
        ),
        _case(
            "runbook-certification",
            l3_runbook,
            replace(l3_policy, certified_runbooks=()),
            l3_request,
            True,
            PolicyControlState(),
            l3_context,
            False,
            PolicyReason.RUNBOOK_CERTIFICATION.value,
        ),
        _case(
            "l3-human-approval",
            l3_runbook,
            l3_policy,
            l3_request,
            False,
            PolicyControlState(),
            l3_context,
            False,
            PolicyReason.HUMAN_APPROVAL.value,
        ),
        _case(
            "l4-error-budget",
            l4_runbook,
            l4_policy,
            replace(l4_request, error_budget_remaining=0.0),
            True,
            PolicyControlState(audit_available=False),
            l4_context,
            False,
            PolicyReason.ERROR_BUDGET.value,
        ),
        _case(
            "l4-certification-absent",
            l4_runbook,
            l4_policy,
            l4_request,
            True,
            PolicyControlState(),
            replace(l4_context, certification=None),
            False,
            PolicyReason.CERTIFICATION_ABSENT.value,
        ),
        _case(
            "l4-evaluation-time-unreadable",
            l4_runbook,
            l4_policy,
            l4_request,
            True,
            PolicyControlState(),
            replace(l4_context, now="not-a-time"),
            False,
            PolicyReason.EVALUATION_TIME_UNREADABLE.value,
        ),
        _case(
            "l4-certification-expiry-unreadable",
            l4_runbook,
            l4_policy,
            l4_request,
            True,
            PolicyControlState(),
            replace(
                l4_context,
                certification=replace(valid_claim, expires_on="not-a-time"),
            ),
            False,
            PolicyReason.CERTIFICATION_EXPIRY_UNREADABLE.value,
        ),
        _case(
            "l4-certification-expired",
            l4_runbook,
            l4_policy,
            l4_request,
            True,
            PolicyControlState(),
            replace(
                l4_context,
                certification=replace(valid_claim, expires_on="2026-08-27T00:00:00+00:00"),
            ),
            False,
            PolicyReason.CERTIFICATION_EXPIRED.value,
        ),
        _case(
            "l4-scope-missing",
            l4_runbook,
            l4_policy,
            l4_request,
            True,
            PolicyControlState(),
            replace(l4_context, scope_hash=""),
            False,
            PolicyReason.SCOPE_MISSING.value,
        ),
        _case(
            "l4-scope-mismatch",
            l4_runbook,
            l4_policy,
            l4_request,
            True,
            PolicyControlState(),
            replace(l4_context, scope_hash="scope-b"),
            False,
            PolicyReason.SCOPE_MISMATCH.value,
        ),
        _case(
            "l4-inputs-hash-missing",
            l4_runbook,
            l4_policy,
            l4_request,
            True,
            PolicyControlState(),
            replace(l4_context, certification=replace(valid_claim, inputs_hash="")),
            False,
            PolicyReason.INPUTS_HASH_MISSING.value,
        ),
        _case(
            "audit-control-after-safety-and-certification",
            l4_runbook,
            l4_policy,
            l4_request,
            True,
            PolicyControlState(audit_available=False, verification_defined=False),
            l4_context,
            False,
            PolicyReason.AUDIT_UNAVAILABLE.value,
        ),
        _case(
            "verification-control",
            l4_runbook,
            l4_policy,
            l4_request,
            True,
            PolicyControlState(verification_defined=False),
            l4_context,
            False,
            PolicyReason.VERIFICATION_UNAVAILABLE.value,
        ),
        _case(
            "authorized-l4",
            l4_runbook,
            l4_policy,
            l4_request,
            True,
            PolicyControlState(),
            l4_context,
            True,
            PolicyReason.AUTHORIZED.value,
        ),
        _case(
            "l4-supervised-downgrade-still-requires-approval",
            l4_runbook,
            l4_policy,
            l4_request,
            False,
            PolicyControlState(),
            replace(l4_context, autonomy_level="L3", certification=None),
            False,
            PolicyReason.HUMAN_APPROVAL.value,
        ),
)


def raw_remediation_policy_conformance_cases() -> tuple[RawPolicyConformanceCase, ...]:
    """Return policy inputs rejected before valid domain objects can exist."""

    authorized_l3 = next(
        case for case in remediation_policy_conformance_cases() if case.name == "authorized-l3"
    )
    payload = opa_input(
        runbook=authorized_l3.runbook,
        policy=authorized_l3.policy,
        request=authorized_l3.request,
        approval_verified=authorized_l3.approval_verified,
        control=authorized_l3.control,
        autonomy=authorized_l3.autonomy,
    )
    raw = payload["input"]
    if not isinstance(raw, dict):  # Defensive: opa_input is a public wire contract.
        raise RuntimeError("OPA input builder returned a non-object input")
    policy = raw.get("policy")
    if not isinstance(policy, dict):
        raise RuntimeError("OPA input builder returned a non-object policy")
    requirement = branch_requirement("policy-level-missing")
    if requirement is None:  # Keep the corpus coupled to the branch manifest.
        raise RuntimeError("policy-level branch requirement is absent")
    missing_level = {key: value for key, value in policy.items() if key != "level"}
    return (
        RawPolicyConformanceCase(
            name="policy-level-missing",
            input={**raw, "policy": missing_level},
            allowed=False,
            reason=requirement.reason.value,
            branch=requirement.branch,
        ),
        RawPolicyConformanceCase(
            name="policy-level-non-numeric",
            input={**raw, "policy": {**policy, "level": "4"}},
            allowed=False,
            reason=requirement.reason.value,
            branch=requirement.branch,
        ),
    )


def _case(
    name: str,
    runbook: Runbook,
    policy: ServiceAutonomy,
    request: ActionRequest,
    approval_verified: bool,
    control: PolicyControlState,
    autonomy: AutonomyContext,
    allowed: bool,
    reason: str,
) -> PolicyConformanceCase:
    requirement = branch_requirement(name)
    if requirement is not None and reason != requirement.reason.value:
        raise ValueError(
            f"{name}: expected reason must match {requirement.branch.value} contract branch"
        )
    return PolicyConformanceCase(
        name=name,
        runbook=runbook,
        policy=policy,
        request=request,
        approval_verified=approval_verified,
        control=control,
        autonomy=autonomy,
        allowed=allowed,
        reason=reason,
        branch=requirement.branch if requirement is not None else None,
    )
