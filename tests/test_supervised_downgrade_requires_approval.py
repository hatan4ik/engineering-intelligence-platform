"""The sanctioned L3 downgrade of an L4 scope is still a supervised L3 run.

It skips the L4 certification (supervised exercises are the input to
certification) but never the human approval that L3 means -- at both policy
boundaries, and a fractional level claim is not a level at all.
"""
from __future__ import annotations

from datetime import datetime, timezone

from remediation.catalog import AutonomyLevel, default_catalog
from remediation.executor import execute_control_loop
from remediation.opa_policy import AutonomyContext, LocalReferenceEvaluator, PolicyControlState
from remediation.policy import ActionRequest, ServiceAutonomy

NOW = datetime(2026, 8, 26, tzinfo=timezone.utc)
RUNBOOK_ID = "aks.rollout.undo"


class Adapter:
    def __init__(self) -> None:
        self.executed: list[str] = []

    def execute(self, runbook_id: str, request: ActionRequest) -> str:
        self.executed.append(runbook_id)
        return f"exec-{runbook_id}"

    def verify(self, signal: str, request: ActionRequest) -> bool:
        return True

    def rollback(self, rollback_id: str, request: ActionRequest) -> str:
        return f"rollback-{rollback_id}"


def l4_policy() -> ServiceAutonomy:
    return ServiceAutonomy(
        service="payments",
        environment="prod",
        level=AutonomyLevel.BOUNDED_AUTONOMOUS,
        certified_runbooks=(RUNBOOK_ID,),
        max_blast_radius=5,
        kill_switch=False,
    )


def request() -> ActionRequest:
    return ActionRequest(
        service="payments",
        environment="prod",
        runbook_id=RUNBOOK_ID,
        blast_radius=2,
        error_budget_remaining=1.0,
    )


def run(adapter: Adapter, *, approval_verified: bool, autonomy_level):
    return execute_control_loop(
        catalog=default_catalog(),
        policy=l4_policy(),
        request=request(),
        adapter=adapter,
        evaluator=LocalReferenceEvaluator(),
        approval_verified=approval_verified,
        certification=None,
        autonomy_level=autonomy_level,
        now=NOW,
        environ={},
    )


def test_the_supervised_downgrade_is_refused_without_a_verified_approval():
    adapter = Adapter()
    result = run(adapter, approval_verified=False, autonomy_level=AutonomyLevel.APPROVE_AND_EXECUTE)
    assert result.status == "denied"
    assert "verified human approval is required" in result.policy.reason
    assert adapter.executed == []


def test_the_supervised_downgrade_runs_under_l3_rules_with_a_verified_approval():
    adapter = Adapter()
    result = run(adapter, approval_verified=True, autonomy_level=AutonomyLevel.APPROVE_AND_EXECUTE)
    assert result.status == "succeeded"
    assert adapter.executed == [RUNBOOK_ID]


def test_the_local_evaluator_keys_approval_on_the_effective_level():
    evaluator = LocalReferenceEvaluator()
    runbook = default_catalog().get(RUNBOOK_ID)
    downgraded = AutonomyContext(autonomy_level="L3", now=NOW.isoformat(), policy_level=4)
    denied = evaluator.evaluate(
        runbook=runbook, policy=l4_policy(), request=request(),
        approval_verified=False, control=PolicyControlState(), autonomy=downgraded,
    )
    assert denied.allowed is False
    assert denied.reason == "verified human approval is required"
    allowed = evaluator.evaluate(
        runbook=runbook, policy=l4_policy(), request=request(),
        approval_verified=True, control=PolicyControlState(), autonomy=downgraded,
    )
    assert allowed.allowed is True


def test_effective_level_mirrors_the_rego_rule():
    assert AutonomyContext(autonomy_level="L3", policy_level=4).effective_level == 3
    assert AutonomyContext(autonomy_level="l3", policy_level=4).effective_level == 3
    assert AutonomyContext(autonomy_level="L3", policy_level=3).effective_level == 3
    assert AutonomyContext(autonomy_level="L2", policy_level=4).effective_level == 4
    assert AutonomyContext(autonomy_level=None, policy_level=4).effective_level == 4  # type: ignore[arg-type]
    assert AutonomyContext(autonomy_level=4, policy_level=4).effective_level == 4  # type: ignore[arg-type]


def test_a_fractional_level_claim_is_refused_rather_than_truncated():
    adapter = Adapter()
    result = run(adapter, approval_verified=True, autonomy_level=3.9)
    assert result.status == "blocked"
    assert "is not an autonomy level" in result.policy.reason
    assert adapter.executed == []
