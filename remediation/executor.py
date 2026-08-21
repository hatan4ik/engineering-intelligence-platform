from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .catalog import RunbookCatalog
from .policy import ActionRequest, PolicyDecision, ServiceAutonomy, authorize


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


def execute_control_loop(
    *,
    catalog: RunbookCatalog,
    policy: ServiceAutonomy,
    request: ActionRequest,
    adapter: ActionAdapter,
) -> ExecutionResult:
    runbook = catalog.get(request.runbook_id)
    decision = authorize(runbook, policy, request)
    if not decision.allowed:
        return ExecutionResult(status="denied", policy=decision)

    execution_ref = adapter.execute(runbook.id, request)
    verified = adapter.verify(runbook.verify_signal, request)
    if verified:
        return ExecutionResult(
            status="succeeded",
            policy=decision,
            execution_ref=execution_ref,
            verified=True,
        )

    rollback_ref = None
    if runbook.rollback_id:
        rollback_ref = adapter.rollback(runbook.rollback_id, request)
    return ExecutionResult(
        status="rolled_back" if rollback_ref else "escalate",
        policy=decision,
        execution_ref=execution_ref,
        verified=False,
        rollback_ref=rollback_ref,
    )
