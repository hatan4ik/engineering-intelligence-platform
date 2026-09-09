from __future__ import annotations


from remediation.canary import CanaryStrategy, ProgressiveCanaryExecutor
from remediation.catalog import AutonomyLevel, default_catalog
from remediation.executor import execute_control_loop
from remediation.policy import ActionRequest, ServiceAutonomy


class _CanaryTestAdapter:
    def __init__(self, canary_succeeds: bool = True, fleet_succeeds: bool = True) -> None:
        self.canary_succeeds = canary_succeeds
        self.fleet_succeeds = fleet_succeeds
        self.executed: list[str] = []
        self.verified: list[str] = []
        self.rolled_back: list[str] = []

    def execute(self, runbook_id: str, request: ActionRequest) -> str:
        self.executed.append(runbook_id)
        return f"exec-{runbook_id}"

    def verify(self, signal: str, request: ActionRequest) -> bool:
        self.verified.append(signal)
        if "canary" in signal:
            return self.canary_succeeds
        return self.fleet_succeeds

    def rollback(self, rollback_id: str, request: ActionRequest) -> str:
        self.rolled_back.append(rollback_id)
        return f"rollback-{rollback_id}"


def test_progressive_canary_promotes_when_canary_verifies() -> None:
    catalog = default_catalog()
    runbook = catalog.get("aks.restart.workload")
    request = ActionRequest("cart-service", "stage", runbook.id, blast_radius=1)
    adapter = _CanaryTestAdapter(canary_succeeds=True, fleet_succeeds=True)
    executor = ProgressiveCanaryExecutor(adapter)

    strategy = CanaryStrategy(canary_percentage=10, canary_verify_signal="deployment.canary_ready")
    result = executor.execute_progressive(runbook, request, strategy)

    assert result.status == "succeeded"
    assert result.canary_verified is True
    assert result.fleet_verified is True
    assert "aks.restart.workload.canary" in adapter.executed
    assert "aks.restart.workload" in adapter.executed
    assert len(adapter.rolled_back) == 0


def test_progressive_canary_aborts_without_touching_fleet_when_canary_fails() -> None:
    catalog = default_catalog()
    runbook = catalog.get("aks.rollback.readiness")
    request = ActionRequest("cart-service", "stage", runbook.id, blast_radius=1)
    adapter = _CanaryTestAdapter(canary_succeeds=False, fleet_succeeds=True)
    executor = ProgressiveCanaryExecutor(adapter)

    strategy = CanaryStrategy(canary_percentage=10, canary_verify_signal="deployment.canary_ready")
    result = executor.execute_progressive(runbook, request, strategy)

    assert result.status == "aborted"
    assert result.canary_verified is False
    assert result.fleet_verified is False
    assert "aks.rollback.readiness.canary" in adapter.executed
    # Main fleet was NEVER executed!
    assert "aks.rollback.readiness" not in adapter.executed
    # Canary was safely rolled back
    assert "aks.rollout.redo" in adapter.rolled_back


def test_execute_control_loop_integrates_canary_strategy() -> None:
    catalog = default_catalog()
    policy = ServiceAutonomy("orders-api", "stage", AutonomyLevel.APPROVE_AND_EXECUTE, ("aks.restart.workload",), 5)
    request = ActionRequest("orders-api", "stage", "aks.restart.workload", blast_radius=1)
    adapter = _CanaryTestAdapter(canary_succeeds=True, fleet_succeeds=True)
    strategy = CanaryStrategy(canary_percentage=5, canary_verify_signal="deployment.canary_ready")

    result = execute_control_loop(
        catalog=catalog,
        policy=policy,
        request=request,
        adapter=adapter,
        approval_verified=True,
        canary_strategy=strategy,
    )

    assert result.status == "succeeded"
    assert result.verified is True
    assert result.execution_ref == "canary-fleet-promoted"
    assert "aks.restart.workload.canary" in adapter.executed
    assert "aks.restart.workload" in adapter.executed
