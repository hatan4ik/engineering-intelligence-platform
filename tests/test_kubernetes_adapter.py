import json

from remediation.catalog import AutonomyLevel, default_catalog
from remediation.executor import execute_control_loop
from remediation.kubernetes_adapter import CommandResult, KubernetesActionAdapter
from remediation.policy import ActionRequest, ServiceAutonomy


class FakeRunner:
    def __init__(self, *, final_ready=True):
        self.calls = []
        self.final_ready = final_ready
        self.mutated = False

    def run(self, argv):
        argv = tuple(argv)
        self.calls.append(argv)
        if argv[-3:] == ("rollout", "history", "deployment/payments"):
            return CommandResult(0, "REVISION  CHANGE-CAUSE\n1 old\n2 current\n")
        if "get" in argv and "deployment/payments" in argv:
            replicas = 2 if self.mutated and self.final_ready else 0
            return CommandResult(
                0,
                json.dumps({
                    "metadata": {"annotations": {}},
                    "spec": {"replicas": 2},
                    "status": {"availableReplicas": replicas, "readyReplicas": replicas},
                }),
            )
        if "get" in argv and "pods" in argv:
            return CommandResult(0, json.dumps({"items": []}))
        if "rollout" in argv and ("restart" in argv or "undo" in argv):
            self.mutated = True
            return CommandResult(0, "ok")
        return CommandResult(0, "ok")


def policy(runbooks=("aks.rollout.undo", "aks.restart.workload")):
    return ServiceAutonomy(
        service="payments",
        environment="prod",
        level=AutonomyLevel.APPROVE_AND_EXECUTE,
        certified_runbooks=runbooks,
        max_blast_radius=3,
    )


def test_restart_preflights_then_uses_fixed_argv_and_independent_verification():
    runner = FakeRunner()
    adapter = KubernetesActionAdapter(runner, namespace="prod")
    request = ActionRequest("payments", "prod", "aks.restart.workload", 2, approval_token="approved")
    result = execute_control_loop(catalog=default_catalog(), policy=policy(), request=request, adapter=adapter, approval_verified=True)
    assert result.status == "succeeded"
    assert runner.calls[0] == ("kubectl", "-n", "prod", "get", "deployment/payments", "-o", "json")
    assert runner.calls[1] == ("kubectl", "-n", "prod", "rollout", "restart", "deployment/payments")
    assert runner.calls[2] == ("kubectl", "-n", "prod", "get", "deployment/payments", "-o", "json")


def test_preflight_blocks_unsafe_names_before_mutation():
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
        approval_verified=True,
    )
    assert result.status == "denied"
    assert "invalid Kubernetes name" in result.error


def test_failed_verification_without_safe_redo_escalates_instead_of_crashing():
    adapter = KubernetesActionAdapter(FakeRunner(final_ready=False), namespace="prod")
    request = ActionRequest("payments", "prod", "aks.rollout.undo", 2, approval_token="x")
    result = execute_control_loop(catalog=default_catalog(), policy=policy(), request=request, adapter=adapter, approval_verified=True)
    assert result.status == "escalate"
    assert "automatic redo is not safely defined" in result.error


def test_crashloop_runbook_requires_live_crashloop_evidence():
    runner = FakeRunner()
    adapter = KubernetesActionAdapter(runner, namespace="prod")
    request = ActionRequest("payments", "prod", "aks.restart.crashloop", 2, approval_token="x")
    result = execute_control_loop(
        catalog=default_catalog(), policy=policy(("aks.restart.crashloop",)), request=request, adapter=adapter,
        approval_verified=True,
    )
    assert result.status == "denied"
    assert "crashloop_present" in result.error
    assert not any("restart" in call for call in runner.calls)
