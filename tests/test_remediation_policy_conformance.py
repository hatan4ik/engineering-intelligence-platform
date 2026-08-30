"""The local policy evaluator conforms to the shared Rego decision corpus."""

from remediation.opa_policy import LocalReferenceEvaluator, opa_input
from remediation.policy_conformance import (
    raw_remediation_policy_conformance_cases,
    remediation_policy_conformance_cases,
)
from remediation.policy_contract import REGO_DENY_BRANCH_REQUIREMENTS


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


def test_local_reference_matches_malformed_wire_level_cases():
    evaluator = LocalReferenceEvaluator()

    for case in raw_remediation_policy_conformance_cases():
        decision = evaluator.evaluate_input(case.input)
        assert (decision.allowed, decision.reason) == (case.allowed, case.reason), case.name


def test_shared_corpus_covers_every_named_rego_deny_branch_once_or_more():
    typed_cases = remediation_policy_conformance_cases()
    raw_cases = raw_remediation_policy_conformance_cases()
    requirements = {requirement.branch: requirement for requirement in REGO_DENY_BRANCH_REQUIREMENTS}
    covered = {case.branch for case in typed_cases if case.branch is not None}
    covered.update(case.branch for case in raw_cases)

    assert covered == set(requirements)
    assert all(case.branch is None or case.reason == requirements[case.branch].reason.value for case in typed_cases)
    assert all(case.reason == requirements[case.branch].reason.value for case in raw_cases)
    assert {case.branch for case in raw_cases} == {
        requirement.branch for requirement in requirements.values() if requirement.boundary_only
    }


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
