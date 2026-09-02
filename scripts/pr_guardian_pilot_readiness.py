"""Explain whether a target checkout is contract-ready for a shadow pilot.

The command is read-only. A zero exit code means the checked-in manifest and
runtime configuration agree; it does not prove GitHub settings, human approval,
or retained evidence and it cannot authorize advisory/enforcement mode.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from product.pr_guardian.pilot_readiness import assess_shadow_pilot_checkout


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config-root",
        type=Path,
        default=Path("."),
        help="trusted target-repository checkout containing .eip pilot/config files",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="emit the machine-readable readiness report",
    )
    args = parser.parse_args(argv)

    report = assess_shadow_pilot_checkout(args.config_root)
    if args.json:
        print(json.dumps(report.to_payload(), indent=2, sort_keys=True))
    else:
        print(
            f"PR Guardian pilot readiness: state={report.state.value} "
            f"repository={report.repository or 'undeclared'} "
            f"pilot={report.pilot_id or 'undeclared'}"
        )
        for check in report.checks:
            print(f"- [{check.state.value}] {check.name}: {check.detail}")
        if report.operator_actions:
            print("Next operator actions:")
            for action in report.operator_actions:
                print(f"- {action}")
        print("advisory_or_enforcement_authorized=false")
        print("operational_evidence_collected=false")

    return 0 if report.contract_ready else 2


if __name__ == "__main__":
    raise SystemExit(main())
