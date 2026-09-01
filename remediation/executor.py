from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Mapping, Protocol

from control_plane.runtime import REFERENCE_MODE, control_plane_mode
from resilience.certification import (
    L4CertificationRecord,
    certification_refusal,
    certification_scope_for,
    material_inputs_hash_for,
)

from .catalog import AutonomyLevel, Runbook, RunbookCatalog
from .opa_policy import (
    AutonomyContext,
    CertificationClaim,
    LocalReferenceEvaluator,
    PolicyControlState,
    PolicyEvaluator,
    as_policy_decision,
    certification_denial,
)
from .policy import ActionRequest, PolicyDecision, ServiceAutonomy


#: Platform-wide autonomy kill switch. When it is engaged no L3 or L4 execution
#: runs, whatever the policy, the approval, or the certification says.
KILL_SWITCH_ENV = "EIP_AUTONOMY_KILL_SWITCH"

#: The refusal reason the kill switch produces. It is a fixed token so an
#: operator can grep for it and a dashboard can count it.
KILL_SWITCH_REASON = "kill-switch"

#: A non-reference process must not silently fall back to the in-process
#: evaluator. This variable may make the reference process stricter, but may
#: never make a Temporal or disabled control-plane mode less strict.
REQUIRE_OPA_ENV = "EIP_REQUIRE_OPA"

#: Prefix on refusals that come from the declared autonomy level itself.
AUTONOMY_LEVEL_CHECK = "autonomy-level"


def autonomy_kill_switch_engaged(environ: Mapping[str, str] | None = None) -> bool:
    """True when the switch reads ``true``, ignoring case and surrounding whitespace.

    A kill switch errs towards engaged: it must not miss an operator's intent
    because they typed ``TRUE``.
    """

    source = os.environ if environ is None else environ
    return str(source.get(KILL_SWITCH_ENV, "false")).strip().lower() == "true"


def opa_evaluator_required(environ: Mapping[str, str] | None = None) -> bool:
    """Whether this runtime refuses an absent external OPA evaluator.

    The local evaluator is an offline/reference implementation only. Any
    non-reference control-plane mode requires the OPA boundary even when the
    environment accidentally sets ``EIP_REQUIRE_OPA=false``. Reference mode
    may opt in to the same strictness for integration testing.
    """

    source = os.environ if environ is None else environ
    if control_plane_mode(source) != REFERENCE_MODE:
        return True
    return str(source.get(REQUIRE_OPA_ENV, "false")).strip().lower() == "true"


class ActionAdapter(Protocol):
    def execute(self, runbook_id: str, request: ActionRequest) -> str: ...
    def verify(self, signal: str, request: ActionRequest) -> bool: ...
    def rollback(self, rollback_id: str, request: ActionRequest) -> str: ...


@dataclass(frozen=True)
class ExecutionResult:
    status: str
    policy: PolicyDecision
    execution_ref: str | None = None
    verified: bool = False
    rollback_ref: str | None = None
    error: str | None = None


def _preflight(
    adapter: ActionAdapter, runbook: Runbook, request: ActionRequest
) -> tuple[bool, str]:
    checker = getattr(adapter, "preflight", None)
    if checker is None:
        return True, "adapter has no preflight hook; policy/catalog controls only"
    try:
        result = checker(runbook, request)
    except Exception as exc:
        return False, f"precondition evaluation failed: {type(exc).__name__}: {exc}"
    if isinstance(result, tuple):
        allowed, reason = result
        return bool(allowed), str(reason)
    return bool(
        result
    ), "runbook preconditions satisfied" if result else "runbook preconditions failed"


def _claimed_level_value(declared: AutonomyLevel | int | None) -> int:
    """The declared level as a plain int, or 0 when it is not a number at all.

    Used only by the kill switch, which must see the *raw* claim: an
    over-declaration is refused a moment later, but with the switch engaged the
    operator is owed ``kill-switch`` as the reason rather than a level quibble.
    """

    if isinstance(declared, AutonomyLevel):
        return int(declared)
    if type(declared) is int:
        return declared
    return 0


def _effective_level(
    declared: AutonomyLevel | int | None, policy: ServiceAutonomy
) -> tuple[AutonomyLevel, str | None]:
    """Resolve the level a request actually runs at from the level it claims.

    The reviewed service policy is the authority; the declared level is a claim.
    A caller may claim the policy's own level, or make exactly one downgrade --
    running an L4-policy request as a supervised L3, which is the exercise path
    the promotion rule requires. Every other divergence is refused, naming both
    levels, because silently honouring it would let a caller execute an
    uncertified L4 mutation and step around the kill switch.
    """

    granted = policy.level
    if declared is None:
        return granted, None
    not_a_level = (
        f"{AUTONOMY_LEVEL_CHECK}: declared autonomy level {declared!r} is not an "
        f"autonomy level; the reviewed service policy grants L{int(granted)}"
    )
    # A fractional claim is not a level; int() would silently truncate 3.9 to L3.
    if isinstance(declared, float) and not declared.is_integer():
        return granted, not_a_level
    try:
        claimed = AutonomyLevel(int(declared))
    except (TypeError, ValueError):
        return granted, not_a_level
    if claimed == granted:
        return granted, None
    if claimed > granted:
        return granted, (
            f"{AUTONOMY_LEVEL_CHECK}: declared L{int(claimed)} exceeds the reviewed "
            f"service policy level L{int(granted)}"
        )
    if (
        claimed == AutonomyLevel.APPROVE_AND_EXECUTE
        and granted == AutonomyLevel.BOUNDED_AUTONOMOUS
    ):
        # The one sanctioned downgrade: a supervised exercise of an L4 scope.
        return claimed, None
    return granted, (
        f"{AUTONOMY_LEVEL_CHECK}: declared L{int(claimed)} is not a permitted downgrade "
        f"from the reviewed service policy level L{int(granted)}"
    )


def _autonomy_context(
    *,
    level: AutonomyLevel,
    policy: ServiceAutonomy,
    request: ActionRequest,
    runbook: Runbook,
    certification: L4CertificationRecord | None,
    now: datetime,
) -> AutonomyContext:
    """What the policy boundary is told about this request's autonomy."""

    try:
        scope_hash = certification_scope_for(
            policy=policy, request=request, runbook=runbook
        ).scope_hash()
    except ValueError:
        # No bounded budget means no certifiable scope; an empty scope hash
        # matches nothing, so the policy boundary denies rather than guesses.
        scope_hash = ""
    return AutonomyContext(
        autonomy_level=f"L{int(level)}",
        scope_hash=scope_hash,
        now=now.isoformat(),
        # The reviewed policy level travels with the claim so the policy
        # boundary can refuse to be talked out of asking for a certification.
        policy_level=int(policy.level),
        certification=(
            CertificationClaim(
                scope_hash=certification.scope_hash,
                inputs_hash=certification.inputs_hash,
                expires_on=certification.expires_on,
            )
            if certification is not None
            else None
        ),
    )


def _certification_refusal(
    certification: L4CertificationRecord | None,
    *,
    policy: ServiceAutonomy,
    request: ActionRequest,
    runbook: Runbook,
    policy_bundle_version: str,
    now: datetime,
) -> str | None:
    """Why this L4 request is not covered by a certification, or ``None``."""

    try:
        scope = certification_scope_for(policy=policy, request=request, runbook=runbook)
    except ValueError as exc:
        # An unbounded (or zero) blast-radius budget is not a certifiable scope,
        # so an L4 request under such a policy can never be covered.
        return f"l4-certification: {exc}"
    return certification_refusal(
        certification,
        scope_hash=scope.scope_hash(),
        inputs_hash=material_inputs_hash_for(
            scope, runbook, policy_bundle_version=policy_bundle_version
        ),
        now=now,
    )


def execute_control_loop(
    *,
    catalog: RunbookCatalog,
    policy: ServiceAutonomy,
    request: ActionRequest,
    adapter: ActionAdapter,
    evaluator: PolicyEvaluator | None = None,
    approval_verified: bool = False,
    control: PolicyControlState | None = None,
    certification: L4CertificationRecord | None = None,
    autonomy_level: AutonomyLevel | int | None = None,
    now: datetime | None = None,
    environ: Mapping[str, str] | None = None,
) -> ExecutionResult:
    """Run the bounded control loop for one request.

    ``autonomy_level`` is the level this request *claims* to be executed at. The
    reviewed service policy is the authority: an absent claim resolves to
    ``policy.level``, and the only divergence honoured is the one sanctioned
    downgrade -- running an L4-policy request as a supervised L3, which is the
    exercise path. Every other divergence, above or below, is refused with a
    reason naming both levels. The kill switch keys off the higher of the two,
    so a downgrade cannot step around it.

    ``certification`` is the only authority an L4 execution accepts. Its
    presence, expiry and scope are decided before the policy service is
    contacted; its material-inputs hash is compared afterwards, because that
    hash binds the policy bundle revision that authorised the request and the
    revision is only known once the decision comes back.

    ``now`` and ``environ`` exist so expiry and the kill switch are testable
    without touching the clock or the process environment.
    """

    runbook = catalog.get(request.runbook_id)
    level, level_refusal = _effective_level(autonomy_level, policy)
    moment = now or datetime.now(timezone.utc)

    # Fail closed first: the kill switch outranks every other control, including
    # a complete and valid certification and a refused level claim. It keys off
    # the higher of the granted level and the *raw* declared one, so neither a
    # downgrade nor an over-declaration escapes it.
    switch_level = max(int(policy.level), _claimed_level_value(autonomy_level))
    if switch_level >= int(
        AutonomyLevel.APPROVE_AND_EXECUTE
    ) and autonomy_kill_switch_engaged(environ):
        return ExecutionResult(
            status="blocked",
            policy=PolicyDecision(False, KILL_SWITCH_REASON),
            error=f"{KILL_SWITCH_ENV} is engaged; no L3 or L4 execution runs",
        )
    if level_refusal is not None:
        return ExecutionResult(
            status="blocked",
            policy=PolicyDecision(False, level_refusal),
            error=level_refusal,
        )
    if evaluator is None and opa_evaluator_required(environ):
        decision = PolicyDecision(
            False, "OPA policy evaluator is required but not configured"
        )
        return ExecutionResult(status="denied", policy=decision)
    evaluator = evaluator or LocalReferenceEvaluator()
    autonomy = _autonomy_context(
        level=level,
        policy=policy,
        request=request,
        runbook=runbook,
        certification=certification,
        now=moment,
    )
    # Presence, expiry and scope are decidable without asking anyone, so they are
    # decided here: an L4 request that presents no usable certification never
    # reaches the policy service at all.
    if level >= AutonomyLevel.BOUNDED_AUTONOMOUS:
        denial = certification_denial(autonomy)
        if denial is not None:
            return ExecutionResult(
                status="blocked", policy=PolicyDecision(False, denial), error=denial
            )

    # approval_verified must be produced by verify_approval() upstream and passed
    # in explicitly. The presence of an approval_token string is NOT proof of a
    # verified approval and must never satisfy the human-approval gate.
    evaluated = evaluator.evaluate(
        runbook=runbook,
        policy=policy,
        request=request,
        approval_verified=approval_verified,
        control=control or PolicyControlState(),
        # OPA is a separate authorization boundary: it is told the level and the
        # certification claim so it can deny an uncertified L4 mutation itself
        # rather than trusting that this process already did.
        autonomy=autonomy,
    )
    decision = as_policy_decision(evaluated)
    if not decision.allowed:
        return ExecutionResult(status="denied", policy=decision)

    # The material-inputs hash binds the policy bundle revision that authorised
    # this request, so it can only be checked once that revision is known.
    if level >= AutonomyLevel.BOUNDED_AUTONOMOUS:
        refusal = _certification_refusal(
            certification,
            policy=policy,
            request=request,
            runbook=runbook,
            policy_bundle_version=evaluated.policy_revision,
            now=moment,
        )
        if refusal is not None:
            return ExecutionResult(
                status="blocked", policy=PolicyDecision(False, refusal), error=refusal
            )

    preflight_allowed, preflight_reason = _preflight(adapter, runbook, request)
    if not preflight_allowed:
        return ExecutionResult(
            status="denied",
            policy=PolicyDecision(False, preflight_reason),
            error=preflight_reason,
        )

    try:
        execution_ref = adapter.execute(runbook.id, request)
    except Exception as exc:
        return ExecutionResult(
            status="escalate",
            policy=decision,
            error=f"execution failed: {type(exc).__name__}: {exc}",
        )

    verification_error: str | None
    try:
        verified = adapter.verify(runbook.verify_signal, request)
    except Exception as exc:
        verified = False
        verification_error = f"verification failed: {type(exc).__name__}: {exc}"
    else:
        verification_error = None

    if verified:
        return ExecutionResult(
            status="succeeded",
            policy=decision,
            execution_ref=execution_ref,
            verified=True,
        )

    rollback_ref = None
    rollback_error = None
    if runbook.rollback_id:
        try:
            rollback_ref = adapter.rollback(runbook.rollback_id, request)
        except Exception as exc:
            rollback_error = f"rollback failed: {type(exc).__name__}: {exc}"

    error = "; ".join(e for e in (verification_error, rollback_error) if e) or None
    return ExecutionResult(
        status="rolled_back" if rollback_ref else "escalate",
        policy=decision,
        execution_ref=execution_ref,
        verified=False,
        rollback_ref=rollback_ref,
        error=error,
    )
