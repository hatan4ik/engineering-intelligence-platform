"""Compare every shared remediation-policy case against OPA and local reference.

Run this against a reachable OPA server that loaded
``infra/policy/remediation-policy.rego``. It deliberately compares only the
authorization verdict and reason: the policy revision identifies different
implementations and is not expected to be equal.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


# Support both ``python scripts/...`` from a checkout and CI invocation with a
# configured PYTHONPATH.  The policy modules are repository packages, not
# dependencies installed by this verification script.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from remediation.opa_policy import LocalReferenceEvaluator, OpaPolicyClient
from remediation.policy_conformance import (
    raw_remediation_policy_conformance_cases,
    remediation_policy_conformance_cases,
)
from remediation.policy_contract import REGO_DENY_BRANCH_REQUIREMENTS


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--opa-endpoint", required=True, help="OPA server URL, for example http://127.0.0.1:8181")
    args = parser.parse_args(argv)

    authoritative = OpaPolicyClient(args.opa_endpoint)
    local = LocalReferenceEvaluator()
    typed_cases = remediation_policy_conformance_cases()
    raw_cases = raw_remediation_policy_conformance_cases()
    failures: list[str] = []
    required_branches = {requirement.branch for requirement in REGO_DENY_BRANCH_REQUIREMENTS}
    covered_branches = {
        case.branch for case in typed_cases if case.branch is not None
    } | {case.branch for case in raw_cases}
    if covered_branches != required_branches:
        failures.append(
            "branch corpus mismatch: "
            f"missing={sorted(required_branches - covered_branches)!r}; "
            f"unexpected={sorted(covered_branches - required_branches)!r}"
        )
    for case in typed_cases:
        kwargs = {
            "runbook": case.runbook,
            "policy": case.policy,
            "request": case.request,
            "approval_verified": case.approval_verified,
            "control": case.control,
            "autonomy": case.autonomy,
        }
        opa = authoritative.evaluate(**kwargs)
        reference = local.evaluate(**kwargs)
        expected = (case.allowed, case.reason)
        actual_opa = (opa.allowed, opa.reason)
        actual_reference = (reference.allowed, reference.reason)
        if actual_opa != expected or actual_reference != expected:
            failures.append(
                f"{case.name}: expected {expected!r}; OPA={actual_opa!r}; "
                f"local={actual_reference!r}"
            )
    for case in raw_cases:
        opa = authoritative.evaluate_input({"input": case.input})
        reference = local.evaluate_input(case.input)
        expected = (case.allowed, case.reason)
        actual_opa = (opa.allowed, opa.reason)
        actual_reference = (reference.allowed, reference.reason)
        if actual_opa != expected or actual_reference != expected:
            failures.append(
                f"{case.name}: expected {expected!r}; OPA={actual_opa!r}; "
                f"local={actual_reference!r}"
            )
    if failures:
        print("remediation policy conformance failed:")
        print("\n".join(f"- {failure}" for failure in failures))
        return 1
    print(
        "remediation policy conformance verified for "
        f"{len(typed_cases)} typed and {len(raw_cases)} wire-boundary cases"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
