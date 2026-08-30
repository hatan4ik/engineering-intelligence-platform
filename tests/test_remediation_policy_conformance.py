"""The local policy evaluator conforms to the shared Rego decision corpus."""

from remediation.opa_policy import LocalReferenceEvaluator, opa_input
from remediation.policy_conformance import remediation_policy_conformance_cases


def test_local_reference_matches_every_documented_rego_contract_case():
    evaluator = LocalReferenceEvaluator()

    for case in remediation_policy_conformance_cases():
        decision = evaluator.evaluate(
            runbook=case.runbook,
            policy=case.policy,
            request=case.request,
            approval_verified=case.approval_verified,
            control=case.control,
            autonomy=case.autonomy,
        )
        assert (decision.allowed, decision.reason) == (case.allowed, case.reason), case.name


def test_opa_input_builder_preserves_the_same_typed_case_context():
    case = next(item for item in remediation_policy_conformance_cases() if item.name == "authorized-l4")

    payload = opa_input(
        runbook=case.runbook,
        policy=case.policy,
        request=case.request,
        approval_verified=case.approval_verified,
        control=case.control,
        autonomy=case.autonomy,
    )["input"]

    assert payload["autonomy_level"] == "L4"
    assert payload["scope"] == {"scope_hash": "scope-a"}
    assert payload["certification"] == {
        "scope_hash": "scope-a",
        "inputs_hash": "inputs-a",
        "expires_on": "2026-09-01T00:00:00+00:00",
    }
