"""Validate the canonical performance budget and its rendered documentation.

This verifies a target contract.  It does not run a workload and cannot report
that any target has been observed or that a production gate has passed.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from validation.performance_contract import (
    PerformanceContractError,
    load_performance_baseline,
    render_contract_tables,
    rendered_document_matches,
)


DEFAULT_BASELINE = ROOT / "requirements" / "performance-baseline.json"
DEFAULT_DOCUMENT = ROOT / "docs" / "PERFORMANCE-EVIDENCE-CONTRACT.md"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--document", type=Path, default=DEFAULT_DOCUMENT)
    parser.add_argument("--check-rendered", action="store_true")
    parser.add_argument("--print-rendered", action="store_true")
    args = parser.parse_args(argv)
    try:
        baseline = load_performance_baseline(args.baseline)
        if args.check_rendered and not rendered_document_matches(args.document, baseline):
            print(
                f"rendered performance tables in {args.document} do not match {args.baseline}",
                file=sys.stderr,
            )
            return 1
    except PerformanceContractError as error:
        print(str(error), file=sys.stderr)
        return 2
    if args.print_rendered:
        print(render_contract_tables(baseline))
    else:
        print(
            f"performance contract verified: status={baseline.status} contracts={len(baseline.contracts)} "
            "(targets only; no operational evidence implied)"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
