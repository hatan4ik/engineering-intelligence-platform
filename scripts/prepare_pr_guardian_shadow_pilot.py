"""Prepare validated PR Guardian shadow-pilot source files for human review.

The command never calls GitHub and never enables a pilot. By default it prints
a validated bundle. With ``--write-root`` it creates the two `.eip` files only
when neither already exists, so an operator cannot silently overwrite a
repository-owned decision.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from product.pr_guardian.pilot import PilotDataClassification
from product.pr_guardian.pilot_bootstrap import build_shadow_pilot_bundle


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--service-id", action="append", required=True, dest="service_ids")
    parser.add_argument("--owner-id", action="append", required=True, dest="owner_ids")
    parser.add_argument("--policy-version", default="pr-policy-v1")
    parser.add_argument(
        "--data-classification",
        choices=[item.value for item in PilotDataClassification],
        required=True,
    )
    parser.add_argument("--evidence-system", required=True)
    parser.add_argument("--evidence-locator", required=True)
    parser.add_argument("--evidence-access-control-ref", required=True)
    parser.add_argument("--evidence-immutability-control-ref", required=True)
    parser.add_argument("--pilot-owner", required=True)
    parser.add_argument("--security-reviewer", required=True)
    parser.add_argument("--developer-experience-owner", required=True)
    parser.add_argument("--pilot-id", default=None)
    parser.add_argument("--reviewer-disposition-sla-hours", type=int, default=72)
    parser.add_argument("--hypercare-days", type=int, default=14)
    parser.add_argument(
        "--write-root",
        type=Path,
        default=None,
        help="optional trusted target checkout; creates .eip files without overwriting existing decisions",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    bundle = build_shadow_pilot_bundle(
        repository=args.repository,
        service_ids=tuple(args.service_ids),
        owner_ids=tuple(args.owner_ids),
        policy_version=args.policy_version,
        data_classification=PilotDataClassification(args.data_classification),
        evidence_system=args.evidence_system,
        evidence_locator=args.evidence_locator,
        evidence_access_control_ref=args.evidence_access_control_ref,
        evidence_immutability_control_ref=args.evidence_immutability_control_ref,
        pilot_owner=args.pilot_owner,
        security_reviewer=args.security_reviewer,
        developer_experience_owner=args.developer_experience_owner,
        pilot_id=args.pilot_id,
        reviewer_disposition_sla_hours=args.reviewer_disposition_sla_hours,
        hypercare_days=args.hypercare_days,
    )

    if args.write_root is None:
        print(json.dumps(bundle.to_payload(), indent=2, sort_keys=True))
        return 0

    eip = args.write_root / ".eip"
    manifest_path = eip / "pr-guardian-shadow-pilot.json"
    config_path = eip / "pr-guardian.json"
    existing = [str(path) for path in (manifest_path, config_path) if path.exists()]
    if existing:
        print(
            "refusing to overwrite repository-owned pilot files: " + ", ".join(existing),
            file=sys.stderr,
        )
        return 2
    eip.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(bundle.manifest.to_payload(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    config_path.write_text(
        json.dumps(bundle.runtime_configuration, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"prepared review-only pilot files under {eip}")
    print("advisory_or_enforcement_authorized=false")
    print("operational_evidence_collected=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
