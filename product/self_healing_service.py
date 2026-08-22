from __future__ import annotations

from dataclasses import dataclass

from intelligence.incidents import IncidentAnalysis
from remediation.catalog import RunbookCatalog
from remediation.executor import ActionAdapter, ExecutionResult, execute_control_loop
from remediation.planner import RemediationPlan, plan_from_incident
from remediation.policy import ActionRequest, ServiceAutonomy
from remediation.simulation import SimulationResult, simulate


@dataclass(frozen=True)
class SelfHealingResult:
    status: str
    plan: RemediationPlan | None
    simulation: SimulationResult | None
    execution: ExecutionResult | None


class SelfHealingService:
    """Guardrailed bridge from incident intelligence to certified remediation.

    Planning is deterministic, policy remains authoritative, and risky actions
    may be simulation-gated before execution. The action adapter is the only
    mutation boundary.
    """

    def __init__(
        self,
        *,
        catalog: RunbookCatalog,
        policy: ServiceAutonomy,
        adapter: ActionAdapter,
        sandbox_adapter: ActionAdapter | None = None,
    ) -> None:
        self.catalog = catalog
        self.policy = policy
        self.adapter = adapter
        self.sandbox_adapter = sandbox_adapter

    def handle_incident(
        self,
        analysis: IncidentAnalysis,
        *,
        blast_radius: int,
        approval_token: str | None = None,
        error_budget_remaining: float = 1.0,
        require_simulation: bool = True,
    ) -> SelfHealingResult:
        plan = plan_from_incident(analysis)
        if plan is None:
            return SelfHealingResult("no-certified-plan", None, None, None)

        request = ActionRequest(
            service=self.policy.service,
            environment=self.policy.environment,
            runbook_id=plan.runbook_id,
            blast_radius=blast_radius,
            approval_token=approval_token,
            error_budget_remaining=error_budget_remaining,
        )

        simulation_result = None
        if require_simulation:
            if self.sandbox_adapter is None:
                return SelfHealingResult("simulation-required", plan, None, None)
            simulation_result = simulate(
                catalog=self.catalog,
                policy=self.policy,
                request=request,
                sandbox_adapter=self.sandbox_adapter,
            )
            if not simulation_result.safe_to_promote:
                return SelfHealingResult("simulation-blocked", plan, simulation_result, None)

        execution = execute_control_loop(
            catalog=self.catalog,
            policy=self.policy,
            request=request,
            adapter=self.adapter,
        )
        return SelfHealingResult(execution.status, plan, simulation_result, execution)
