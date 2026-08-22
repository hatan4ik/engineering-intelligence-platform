from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Protocol

from .catalog import RunbookCatalog
from .opa_policy import LocalReferenceEvaluator, PolicyControlState, PolicyEvaluator, as_policy_decision
from .policy import ActionRequest, PolicyDecision, ServiceAutonomy


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


def execute_control_loop(
    *,
    catalog: RunbookCatalog,
    policy: ServiceAutonomy,
    request: ActionRequest,
    adapter: ActionAdapter,
    evaluator: PolicyEvaluator | None = None,
    approval_verified: bool | None = None,
    control: PolicyControlState | None = None,
) -> ExecutionResult:
    runbook = catalog.get(request.runbook_id)
    if evaluator is None and os.getenv("EIP_REQUIRE_OPA", "false").lower() == "true":
        decision = PolicyDecision(False, "OPA policy evaluator is required but not configured")
        return ExecutionResult(status="denied", policy=decision)
    evaluator = evaluator or LocalReferenceEvaluator()
    evaluated = evaluator.evaluate(
        runbook=runbook,
        policy=policy,
        request=request,
        approval_verified=bool(request.approval_token) if approval_verified is None else approval_verified,
        control=control or PolicyControlState(),
    )
    decision = as_policy_decision(evaluated)
    if not decision.allowed:
        return ExecutionResult(status="denied", policy=decision)

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
