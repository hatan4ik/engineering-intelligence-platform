"""Validate one retained performance-observation artifact against its target.

Exit 0 means the artifact is structurally valid and meets its target. Exit 1
means it is valid but does not meet the target. Exit 2 means it is not a valid
artifact. None of these outcomes creates an evidence record or grants a
promotion; use ``scripts/record_evidence.py`` to retain the reviewed result.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from validation.performance_contract import (
    PerformanceContractError,
    assess_performance_observation,
    load_performance_baseline,
    validate_performance_observation,
)


DEFAULT_BASELINE = ROOT / "requirements" / "performance-baseline.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="performance-observation JSON artifact")
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    args = parser.parse_args(argv)
    try:
        baseline = load_performance_baseline(args.baseline)
        payload: object = json.loads(args.input.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise PerformanceContractError("observation: must be a JSON object")
        observation = validate_performance_observation(payload, baseline)
        assessment = assess_performance_observation(observation, baseline)
    except (OSError, json.JSONDecodeError, PerformanceContractError) as error:
        print(f"invalid performance observation: {error}", file=sys.stderr)
        return 2
    print(
        f"performance observation: contract={assessment.contract_id} "
        f"meets_target={assessment.meets_target} basis={observation.basis}"
    )
    for violation in assessment.violations:
        print(f"  - {violation}")
    return 0 if assessment.meets_target else 1


if __name__ == "__main__":
    raise SystemExit(main())
