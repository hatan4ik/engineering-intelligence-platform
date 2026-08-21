import json

from remediation.catalog import AutonomyLevel, default_catalog
from remediation.executor import execute_control_loop
from remediation.kubernetes_adapter import CommandResult, KubernetesActionAdapter
from remediation.policy import ActionRequest, ServiceAutonomy


class FakeRunner:
    def __init__(self, *, ready=True):
        self.calls = []
        self.ready = ready

    def run(self, argv):
        self.calls.append(tuple(argv))
        if "get" in argv:
            replicas = 2 if self.ready else 0
            return CommandResult(
                0,
                json.dumps(
                    {
                        "spec": {"replicas": 2},
                        "status": {"availableReplicas": replicas, "readyReplicas": replicas},
                    }
                ),
            )
        return CommandResult(0, "ok")


def policy():
    return ServiceAutonomy(
        service="payments",
        environment="prod",
        level=AutonomyLevel.APPROVE_AND_EXECUTE,
        certified_runbooks=("aks.rollout.undo", "aks.restart.workload"),
        max_blast_radius=3,
    )


def test_restart_uses_fixed_argv_and_independent_read_verification():
    runner = FakeRunner()
    adapter = KubernetesActionAdapter(runner, namespace="prod")
    request = ActionRequest(
        "payments", "prod", "aks.restart.workload", 2, approval_token="approved"
    )
    result = execute_control_loop(
        catalog=default_catalog(), policy=policy(), request=request, adapter=adapter
    )
    assert result.status == "succeeded"
    assert runner.calls[0] == (
        "kubectl", "-n", "prod", "rollout", "restart", "deployment/payments"
    )
    assert runner.calls[1] == (
        "kubectl", "-n", "prod", "get", "deployment/payments", "-o", "json"
    )


def test_unknown_runbook_and_unsafe_names_cannot_be_interpolated():
    adapter = KubernetesActionAdapter(FakeRunner(), namespace="prod")
    request = ActionRequest("payments;rm -rf /", "prod", "aks.restart.workload", 1, approval_token="x")
    result = execute_control_loop(
        catalog=default_catalog(),
        policy=ServiceAutonomy(
            service=request.service,
            environment="prod",
            level=AutonomyLevel.APPROVE_AND_EXECUTE,
            certified_runbooks=("aks.restart.workload",),
            max_blast_radius=1,
        ),
        request=request,
        adapter=adapter,
    )
    assert result.status == "escalate"
    assert "invalid Kubernetes name" in result.error


def test_failed_verification_without_safe_redo_escalates_instead_of_crashing():
    adapter = KubernetesActionAdapter(FakeRunner(ready=False), namespace="prod")
    request = ActionRequest("payments", "prod", "aks.rollout.undo", 2, approval_token="x")
    result = execute_control_loop(
        catalog=default_catalog(), policy=policy(), request=request, adapter=adapter
    )
    assert result.status == "escalate"
    assert "automatic redo is not safely defined" in result.error
