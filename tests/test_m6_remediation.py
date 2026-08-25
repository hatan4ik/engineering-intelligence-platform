from remediation.catalog import AutonomyLevel, default_catalog
from remediation.executor import execute_control_loop
from remediation.policy import ActionRequest, ServiceAutonomy
from remediation.simulation import simulate


class FakeAdapter:
    def __init__(self, verify_result=True):
        self.verify_result = verify_result
        self.calls = []

    def execute(self, runbook_id, request):
        self.calls.append(("execute", runbook_id))
        return "exec-1"

    def verify(self, signal, request):
        self.calls.append(("verify", signal))
        return self.verify_result

    def rollback(self, rollback_id, request):
        self.calls.append(("rollback", rollback_id))
        return "rollback-1"


def policy(level=AutonomyLevel.APPROVE_AND_EXECUTE):
    return ServiceAutonomy(
        service="payments",
        environment="prod",
        level=level,
        certified_runbooks=("aks.rollout.undo", "aks.restart.workload"),
        max_blast_radius=5,
    )


def test_l3_requires_human_approval_token():
    result = execute_control_loop(
        catalog=default_catalog(),
        policy=policy(),
        request=ActionRequest("payments", "prod", "aks.rollout.undo", 3),
        adapter=FakeAdapter(),
    )
    assert result.status == "denied"
    assert "approval" in result.policy.reason


def test_failed_verification_rolls_back():
    adapter = FakeAdapter(verify_result=False)
    result = execute_control_loop(
        catalog=default_catalog(),
        policy=policy(),
        request=ActionRequest("payments", "prod", "aks.rollout.undo", 3, approval_token="approved:abc"),
        adapter=adapter,
        approval_verified=True,
    )
    assert result.status == "rolled_back"
    assert result.rollback_ref == "rollback-1"


def test_digital_twin_blocks_promotion_when_verification_fails():
    result = simulate(
        catalog=default_catalog(),
        policy=policy(),
        request=ActionRequest("payments", "prod", "aks.rollout.undo", 3, approval_token="approved:abc"),
        sandbox_adapter=FakeAdapter(verify_result=False),
        approval_verified=True,
    )
    assert not result.safe_to_promote
