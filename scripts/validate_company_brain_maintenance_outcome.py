"""Validate a non-mutating Company Brain maintenance outcome correlation.

The command accepts a review-only proposal, an explicit human decision, and an
optional later source observation. It does not publish a ticket, query a source
system, modify Company Brain, or claim that the referenced evidence exists.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from company_brain import (
    CompanyBrainMaintenanceError,
    evaluate_maintenance_outcome,
    parse_maintenance_proposal,
    parse_maintenance_review_decision,
    parse_source_revision_observation,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--proposal", required=True, type=Path, help="review-only proposal JSON"
    )
    parser.add_argument(
        "--decision", required=True, type=Path, help="explicit reviewer-decision JSON"
    )
    parser.add_argument(
        "--source-observation",
        type=Path,
        default=None,
        help="optional independently observed source-revision JSON",
    )
    args = parser.parse_args(argv)

    try:
        proposal = parse_maintenance_proposal(
            json.loads(args.proposal.read_text(encoding="utf-8"))
        )
        decision = parse_maintenance_review_decision(
            json.loads(args.decision.read_text(encoding="utf-8"))
        )
        observation = (
            parse_source_revision_observation(
                json.loads(args.source_observation.read_text(encoding="utf-8"))
            )
            if args.source_observation is not None
            else None
        )
        outcome = evaluate_maintenance_outcome(proposal, decision, observation)
    except (OSError, json.JSONDecodeError, CompanyBrainMaintenanceError) as error:
        print(f"maintenance outcome is invalid: {error}", file=sys.stderr)
        return 2

    print(json.dumps(outcome.to_payload(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
