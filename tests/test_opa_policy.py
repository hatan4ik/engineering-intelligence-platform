import io
import json
import urllib.error

from remediation.catalog import AutonomyLevel, default_catalog
from remediation.opa_policy import LocalReferenceEvaluator, OpaPolicyClient, PolicyControlState
from remediation.policy import ActionRequest, ServiceAutonomy


def request():
    return ActionRequest("payments", "prod", "aks.rollout.undo", 2, approval_token="verified:workflow")


def policy():
    return ServiceAutonomy(
        "payments", "prod", AutonomyLevel.APPROVE_AND_EXECUTE,
        ("aks.rollout.undo",), 5,
    )


def test_local_reference_requires_verified_approval_not_opaque_token():
    decision = LocalReferenceEvaluator().evaluate(
        runbook=default_catalog().get("aks.rollout.undo"),
        policy=policy(),
        request=request(),
        approval_verified=False,
        control=PolicyControlState(),
    )
    assert not decision.allowed
    assert "verified human approval" in decision.reason


def test_local_reference_fails_closed_when_audit_unavailable():
    decision = LocalReferenceEvaluator().evaluate(
        runbook=default_catalog().get("aks.rollout.undo"),
        policy=policy(),
        request=request(),
        approval_verified=True,
        control=PolicyControlState(audit_available=False),
    )
    assert not decision.allowed
    assert decision.reason == "audit control unavailable"


def test_opa_client_parses_authoritative_decision(monkeypatch):
    captured = {}

    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def read(self):
            return json.dumps({"result": {"allowed": True, "reason": "authorized", "policy_revision": "bundle-42"}}).encode()

    def fake_urlopen(req, timeout):
        captured["payload"] = json.loads(req.data)
        return Response()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    decision = OpaPolicyClient("http://opa:8181").evaluate(
        runbook=default_catalog().get("aks.rollout.undo"),
        policy=policy(),
        request=request(),
        approval_verified=True,
        control=PolicyControlState(),
    )
    assert decision.allowed
    assert decision.policy_revision == "bundle-42"
    assert captured["payload"]["input"]["request"]["approval_verified"] is True


def test_opa_network_failure_denies(monkeypatch):
    def broken(req, timeout):
        raise urllib.error.URLError("down")

    monkeypatch.setattr("urllib.request.urlopen", broken)
    decision = OpaPolicyClient("http://opa:8181").evaluate(
        runbook=default_catalog().get("aks.rollout.undo"),
        policy=policy(),
        request=request(),
        approval_verified=True,
        control=PolicyControlState(),
    )
    assert not decision.allowed
    assert "OPA unavailable" in decision.reason
