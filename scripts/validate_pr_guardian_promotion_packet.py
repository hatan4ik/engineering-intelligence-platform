"""Validate a non-authorizing PR Guardian advisory-review packet.

The command validates packet shape and, when given ``--shadow-report``, binds
the packet summary to that generated report. It makes no network calls and
does not establish that an external evidence record exists or that a reviewer
approved a product-mode change.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from company_brain.product_contracts import ProductContractError
from feedback.pr_guardian_promotion import (
    parse_advisory_promotion_review_packet,
    validate_packet_against_shadow_report,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--packet", required=True, type=Path, help="promotion-review packet JSON"
    )
    parser.add_argument(
        "--shadow-report",
        type=Path,
        default=None,
        help="optional generated pr-guardian-shadow-report.json to bind to the packet",
    )
    args = parser.parse_args(argv)

    try:
        packet_payload = json.loads(args.packet.read_text(encoding="utf-8"))
        packet = parse_advisory_promotion_review_packet(packet_payload)
        report_checked = args.shadow_report is not None
        if args.shadow_report is not None:
            report_payload = json.loads(args.shadow_report.read_text(encoding="utf-8"))
            if not isinstance(report_payload, dict):
                raise ProductContractError("shadow report must be a JSON object")
            validate_packet_against_shadow_report(packet, report_payload)
    except (OSError, json.JSONDecodeError, ProductContractError) as error:
        print(f"promotion-review packet is invalid: {error}", file=sys.stderr)
        return 2

    print(
        "promotion-review packet is valid: "
        f"pilot={packet.pilot_id} repository={packet.repository} "
        f"runtime_mode={packet.runtime_mode} review_state={packet.review_state} "
        f"advisory_or_enforcement_authorized={packet.advisory_or_enforcement_authorized} "
        f"shadow_report_checked={report_checked}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
