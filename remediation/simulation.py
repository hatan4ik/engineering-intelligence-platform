from __future__ import annotations

from dataclasses import dataclass

from .catalog import RunbookCatalog
from .executor import ActionAdapter, ExecutionResult, execute_control_loop
from .policy import ActionRequest, ServiceAutonomy


@dataclass(frozen=True)
class SimulationResult:
    safe_to_promote: bool
    execution: ExecutionResult
    notes: tuple[str, ...]


def simulate(
    *,
    catalog: RunbookCatalog,
    policy: ServiceAutonomy,
    request: ActionRequest,
    sandbox_adapter: ActionAdapter,
    approval_verified: bool = False,
) -> SimulationResult:
    # The sandbox dry-run passes through the same policy gate as production, so
    # the verified-approval flag must be forwarded; an unverified plan is denied
    # here just as it would be in production.
    result = execute_control_loop(
        catalog=catalog,
        policy=policy,
        request=request,
        adapter=sandbox_adapter,
        approval_verified=approval_verified,
    )
    notes = []
    if result.status == "succeeded":
        notes.append("sandbox execution verified")
    else:
        notes.append(f"sandbox execution ended with status={result.status}")
    if not result.verified:
        notes.append("production promotion must remain blocked")
    return SimulationResult(
        safe_to_promote=result.status == "succeeded" and result.verified,
        execution=result,
        notes=tuple(notes),
    )
