from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Mapping, Protocol

from resilience.certification import (
    L4CertificationRecord,
    certification_refusal,
    certification_scope_for,
    material_inputs_hash_for,
)

from .catalog import AutonomyLevel, Runbook, RunbookCatalog
from .opa_policy import LocalReferenceEvaluator, PolicyControlState, PolicyEvaluator, as_policy_decision
from .policy import ActionRequest, PolicyDecision, ServiceAutonomy


#: Platform-wide autonomy kill switch. When it is exactly ``true`` no L3 or L4
#: execution runs, whatever the policy, the approval, or the certification says.
KILL_SWITCH_ENV = "EIP_AUTONOMY_KILL_SWITCH"

#: The refusal reason the kill switch produces. It is a fixed token so an
#: operator can grep for it and a dashboard can count it.
KILL_SWITCH_REASON = "kill-switch"


def autonomy_kill_switch_engaged(environ: Mapping[str, str] | None = None) -> bool:
    """True only when the kill switch is set to exactly ``true`` (case-insensitive)."""

    source = os.environ if environ is None else environ
    return str(source.get(KILL_SWITCH_ENV, "false")).strip().lower() == "true"


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


def _preflight(adapter: ActionAdapter, runbook: Runbook, request: ActionRequest) -> tuple[bool, str]:
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
    return bool(result), "runbook preconditions satisfied" if result else "runbook preconditions failed"


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

    ``autonomy_level`` is the level this request is being executed at. It
    defaults to the reviewed service policy's level, so a caller that says
    nothing is still gated at the level its policy actually grants; a caller may
    pass a lower level explicitly, never a higher one than it operates at.

    ``certification`` is the only authority an L4 execution accepts. It is
    checked *after* the policy decision because a certification is bound to the
    policy bundle revision that authorised the request; a request the policy
    denies is already refused and never reaches the gate.
    """

    runbook = catalog.get(request.runbook_id)
    level = AutonomyLevel(int(autonomy_level)) if autonomy_level is not None else policy.level
    moment = now or datetime.now(timezone.utc)

    # Fail closed first: the kill switch outranks every other control, including
    # a complete and valid certification.
    if level >= AutonomyLevel.APPROVE_AND_EXECUTE and autonomy_kill_switch_engaged(environ):
        return ExecutionResult(
            status="blocked",
            policy=PolicyDecision(False, KILL_SWITCH_REASON),
            error=f"{KILL_SWITCH_ENV} is engaged; no L3 or L4 execution runs",
        )
    if evaluator is None and os.getenv("EIP_REQUIRE_OPA", "false").lower() == "true":
        decision = PolicyDecision(False, "OPA policy evaluator is required but not configured")
        return ExecutionResult(status="denied", policy=decision)
    evaluator = evaluator or LocalReferenceEvaluator()
    # approval_verified must be produced by verify_approval() upstream and passed
    # in explicitly. The presence of an approval_token string is NOT proof of a
    # verified approval and must never satisfy the human-approval gate.
    evaluated = evaluator.evaluate(
        runbook=runbook,
        policy=policy,
        request=request,
        approval_verified=approval_verified,
        control=control or PolicyControlState(),
    )
    decision = as_policy_decision(evaluated)
    if not decision.allowed:
        return ExecutionResult(status="denied", policy=decision)

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
