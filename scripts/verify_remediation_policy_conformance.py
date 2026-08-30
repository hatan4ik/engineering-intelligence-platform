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
from remediation.policy_conformance import remediation_policy_conformance_cases


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--opa-endpoint", required=True, help="OPA server URL, for example http://127.0.0.1:8181")
    args = parser.parse_args(argv)

    authoritative = OpaPolicyClient(args.opa_endpoint)
    local = LocalReferenceEvaluator()
    failures: list[str] = []
    for case in remediation_policy_conformance_cases():
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
    if failures:
        print("remediation policy conformance failed:")
        print("\n".join(f"- {failure}" for failure in failures))
        return 1
    print(
        "remediation policy conformance verified for "
        f"{len(remediation_policy_conformance_cases())} cases"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
