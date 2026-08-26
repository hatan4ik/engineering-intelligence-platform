"""The policy boundary is told the autonomy level and the certification claim.

OPA is a separate authorization boundary, so it must be able to deny an L4
mutation on its own evidence rather than trusting that the caller already did.
"""
from __future__ import annotations

import json

from remediation.catalog import AutonomyLevel, default_catalog
from remediation.executor import execute_control_loop
from remediation.opa_policy import (
    AutonomyContext,
    CertificationClaim,
    LocalReferenceEvaluator,
    OpaPolicyClient,
    PolicyControlState,
)
from remediation.policy import ActionRequest, ServiceAutonomy
from resilience.certification import L4CertificationRecord, certification_scope_for


def request():
    return ActionRequest("payments", "prod", "aks.rollout.undo", 2, error_budget_remaining=1.0)


def policy(level=AutonomyLevel.BOUNDED_AUTONOMOUS):
    return ServiceAutonomy("payments", "prod", level, ("aks.rollout.undo",), 5)


def context(**overrides) -> AutonomyContext:
    fields = {
        "autonomy_level": "L4",
        "scope_hash": "a" * 64,
        "now": "2026-08-26T00:00:00+00:00",
        "certification": CertificationClaim(
            scope_hash="a" * 64, inputs_hash="b" * 64, expires_on="2026-11-01T00:00:00+00:00"
        ),
    }
    fields.update(overrides)
    return AutonomyContext(**fields)


def capture_input(monkeypatch, **evaluate_kwargs) -> dict:
    captured: dict = {}

    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def read(self):
            return json.dumps(
                {"result": {"allowed": True, "reason": "ok", "policy_revision": "bundle-42"}}
            ).encode()

    def fake_urlopen(req, timeout):
        captured["payload"] = json.loads(req.data)
        return Response()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    OpaPolicyClient("http://opa:8181").evaluate(
        runbook=default_catalog().get("aks.rollout.undo"),
        policy=policy(),
        request=request(),
        approval_verified=True,
        control=PolicyControlState(),
        **evaluate_kwargs,
    )
    return captured["payload"]["input"]


def test_the_opa_input_carries_the_autonomy_level_and_the_certification(monkeypatch):
    document = capture_input(monkeypatch, autonomy=context())
    assert document["autonomy_level"] == "L4"
    assert document["certification"] == {
        "scope_hash": "a" * 64,
        "inputs_hash": "b" * 64,
        "expires_on": "2026-11-01T00:00:00+00:00",
    }
    assert document["scope"] == {"scope_hash": "a" * 64}
    assert document["now"] == "2026-08-26T00:00:00+00:00"


def test_an_uncertified_l4_request_sends_a_null_certification(monkeypatch):
    document = capture_input(monkeypatch, autonomy=context(certification=None))
    assert document["autonomy_level"] == "L4"
    assert document["certification"] is None


def test_without_an_explicit_context_the_level_comes_from_the_service_policy(monkeypatch):
    document = capture_input(monkeypatch)
    assert document["autonomy_level"] == "L4"
    assert document["certification"] is None
    assert document["now"]


def test_the_executor_hands_the_evaluator_the_level_and_the_certification():
    seen: dict = {}

    class Recorder(LocalReferenceEvaluator):
        def evaluate(self, **kwargs):
            seen.update(kwargs)
            return super().evaluate(**kwargs)

    runbook = default_catalog().get("aks.rollout.undo")
    scope = certification_scope_for(policy=policy(), request=request(), runbook=runbook)
    record = L4CertificationRecord(
        scope=scope,
        scope_hash=scope.scope_hash(),
        inputs_hash="b" * 64,
        exercises_digest="sha256:cafe",
        issued_on="2026-08-01T00:00:00+00:00",
        expires_on="2099-01-01T00:00:00+00:00",
        issued_by="security@example.invalid",
    )
    execute_control_loop(
        catalog=default_catalog(),
        policy=policy(),
        request=request(),
        adapter=object(),
        evaluator=Recorder(),
        approval_verified=True,
        autonomy_level=AutonomyLevel.BOUNDED_AUTONOMOUS,
        certification=record,
    )
    autonomy = seen["autonomy"]
    assert autonomy.autonomy_level == "L4"
    assert autonomy.certification.scope_hash == scope.scope_hash()
    assert autonomy.certification.inputs_hash == "b" * 64
    assert autonomy.scope_hash == scope.scope_hash()
    assert autonomy.now


def test_an_uncertified_l4_request_never_reaches_the_policy_service():
    """The policy service is a second boundary, not the first one."""

    calls: list[str] = []

    class Recorder(LocalReferenceEvaluator):
        def evaluate(self, **kwargs):
            calls.append("evaluated")
            return super().evaluate(**kwargs)

    result = execute_control_loop(
        catalog=default_catalog(),
        policy=policy(),
        request=request(),
        adapter=object(),
        evaluator=Recorder(),
        approval_verified=True,
        autonomy_level=AutonomyLevel.BOUNDED_AUTONOMOUS,
    )
    assert result.status == "blocked"
    assert calls == []


def test_the_local_reference_evaluator_denies_l4_without_a_certification():
    decision = LocalReferenceEvaluator().evaluate(
        runbook=default_catalog().get("aks.rollout.undo"),
        policy=policy(),
        request=request(),
        approval_verified=True,
        control=PolicyControlState(),
        autonomy=context(certification=None),
    )
    assert not decision.allowed
    assert decision.reason.startswith("l4-certification:")


def test_the_local_reference_evaluator_denies_an_expired_certification():
    decision = LocalReferenceEvaluator().evaluate(
        runbook=default_catalog().get("aks.rollout.undo"),
        policy=policy(),
        request=request(),
        approval_verified=True,
        control=PolicyControlState(),
        autonomy=context(
            certification=CertificationClaim(
                scope_hash="a" * 64, inputs_hash="b" * 64, expires_on="2026-08-25T00:00:00+00:00"
            )
        ),
    )
    assert not decision.allowed
    assert "expired" in decision.reason


def test_the_local_reference_evaluator_denies_a_certification_for_another_scope():
    decision = LocalReferenceEvaluator().evaluate(
        runbook=default_catalog().get("aks.rollout.undo"),
        policy=policy(),
        request=request(),
        approval_verified=True,
        control=PolicyControlState(),
        autonomy=context(scope_hash="c" * 64),
    )
    assert not decision.allowed
    assert "scope_hash" in decision.reason


def test_the_local_reference_evaluator_allows_a_matching_certification():
    decision = LocalReferenceEvaluator().evaluate(
        runbook=default_catalog().get("aks.rollout.undo"),
        policy=policy(),
        request=request(),
        approval_verified=True,
        control=PolicyControlState(),
        autonomy=context(),
    )
    assert decision.allowed


def test_l3_is_not_asked_for_a_certification():
    decision = LocalReferenceEvaluator().evaluate(
        runbook=default_catalog().get("aks.rollout.undo"),
        policy=policy(AutonomyLevel.APPROVE_AND_EXECUTE),
        request=request(),
        approval_verified=True,
        control=PolicyControlState(),
        autonomy=context(autonomy_level="L3", certification=None),
    )
    assert decision.allowed


def test_a_level_four_policy_is_asked_for_a_certification_even_with_no_declared_level():
    """The bundle must not fall through permissively when the field is absent."""

    decision = LocalReferenceEvaluator().evaluate(
        runbook=default_catalog().get("aks.rollout.undo"),
        policy=policy(),
        request=request(),
        approval_verified=True,
        control=PolicyControlState(),
        autonomy=AutonomyContext(autonomy_level="", scope_hash="a" * 64, now="2026-08-26T00:00:00+00:00"),
    )
    assert not decision.allowed
    assert decision.reason.startswith("l4-certification:")


def test_the_reviewed_policy_level_outranks_a_claimed_low_level():
    decision = LocalReferenceEvaluator().evaluate(
        runbook=default_catalog().get("aks.rollout.undo"),
        policy=policy(),
        request=request(),
        approval_verified=True,
        control=PolicyControlState(),
        autonomy=context(autonomy_level="L2", certification=None),
    )
    assert not decision.allowed
    assert decision.reason.startswith("l4-certification:")


def test_the_sanctioned_supervised_downgrade_is_not_asked_for_a_certification():
    decision = LocalReferenceEvaluator().evaluate(
        runbook=default_catalog().get("aks.rollout.undo"),
        policy=policy(),
        request=request(),
        approval_verified=True,
        control=PolicyControlState(),
        autonomy=context(autonomy_level="L3", certification=None),
    )
    assert decision.allowed
