import json

import pytest

from remediation.catalog import AutonomyLevel, default_catalog
from remediation.digital_twin import KubernetesDigitalTwin
from remediation.kubernetes_adapter import CommandResult
from remediation.policy import ActionRequest, ServiceAutonomy


class Runner:
    def __init__(self, *, fail_apply=False):
        self.calls = []
        self.fail_apply = fail_apply

    def run(self, argv, input_text=None):
        argv = tuple(argv)
        self.calls.append((argv, input_text))
        if len(argv) > 3 and argv[1:3] == ("-n", "prod") and argv[-4:] == ("get", "deployment/payments", "-o", "json"):
            return CommandResult(0, json.dumps({
                "metadata": {"name": "payments", "uid": "prod-uid", "labels": {"app": "payments"}},
                "spec": {
                    "replicas": 1,
                    "selector": {"matchLabels": {"app": "payments"}},
                    "template": {
                        "metadata": {"labels": {"app": "payments"}},
                        "spec": {
                            "serviceAccountName": "payments-prod",
                            "containers": [{"name": "payments", "image": "payments:v2"}],
                        },
                    },
                },
                "status": {"availableReplicas": 0, "readyReplicas": 0},
            }))
        if argv[-3:] == ("rollout", "history", "deployment/payments"):
            return CommandResult(0, "REVISION CHANGE-CAUSE\n1 v1\n2 v2\n")
        if argv[-3:] == ("apply", "-f", "-"):
            if self.fail_apply:
                return CommandResult(1, "", "apply failed")
            clone = json.loads(input_text)
            assert clone["metadata"]["namespace"].startswith("eip-sim-")
            assert clone["spec"]["template"]["spec"]["automountServiceAccountToken"] is False
            assert "serviceAccountName" not in clone["spec"]["template"]["spec"]
            return CommandResult(0, "deployment.apps/payments created")
        if "rollout" in argv:
            return CommandResult(0, "deployment.apps/payments rolled back")
        if argv[-4:] == ("get", "deployment/payments", "-o", "json"):
            return CommandResult(0, json.dumps({
                "spec": {"replicas": 1},
                "status": {"availableReplicas": 1, "readyReplicas": 1},
            }))
        return CommandResult(0, "ok")


def policy():
    return ServiceAutonomy(
        "payments", "prod", AutonomyLevel.APPROVE_AND_EXECUTE,
        ("aks.rollout.undo",), 3,
    )


def request():
    return ActionRequest(
        "payments", "prod", "aks.rollout.undo", 2,
        approval_token="verified:remediation:inc-1",
    )


def test_ephemeral_twin_clones_without_production_identity_and_cleans_up():
    runner = Runner()
    result = KubernetesDigitalTwin(runner).simulate(
        simulation_id="inc-1",
        source_namespace="prod",
        catalog=default_catalog(),
        policy=policy(),
        request=request(),
    )
    assert result.safe_to_promote is True
    assert any(call[0][:3] == ("kubectl", "delete", "namespace") for call in runner.calls)


def test_provision_failure_still_deletes_namespace():
    runner = Runner(fail_apply=True)
    with pytest.raises(RuntimeError, match="apply failed"):
        KubernetesDigitalTwin(runner).provision(
            simulation_id="inc-2", service="payments", source_namespace="prod"
        )
    assert any(call[0][:3] == ("kubectl", "delete", "namespace") for call in runner.calls)
