"""Write one validated evidence record into the registry.

This script records what a run *showed*. It does not decide that anything is
proven, it never edits a status document, and it refuses:

* a record that fails ``validation.evidence_records.validate_record``;
* ``--basis measured`` without ``--source-run-url`` (a measured claim must cite
  the run it was measured from);
* overwriting an existing record — evidence records are immutable, so a
  correction is a new record that supersedes the old one in its ``claim``.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from validation.evidence_records import BASES, DECISIONS, validate_record

DEFAULT_DIRECTORY = "docs/evidence"

EXIT_INVALID_RECORD = 2
EXIT_WOULD_OVERWRITE = 3


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", default=DEFAULT_DIRECTORY)
    parser.add_argument("--evidence-id", required=True, help="lowercase, filename-safe identifier")
    parser.add_argument("--scope", required=True, help="service, environment, region, classification, tier")
    parser.add_argument("--change", required=True, help="git sha, image digest, IaC, model, prompt, policy, runbook")
    parser.add_argument("--claim", required=True, help="the exact requirement or control being proven")
    parser.add_argument("--method", required=True, help="test, drill, shadow sample, restore, observed window")
    parser.add_argument("--result", required=True, help="pass/fail, quantities, timestamps, population, limits")
    parser.add_argument("--independence", required=True, help="who verified and why the signal is independent")
    parser.add_argument("--artifact", action="append", default=[], required=True, help="repeatable signed link or digest")
    parser.add_argument("--approval", required=True, help="owner, reviewer, expiry, waiver reference")
    # No argparse ``choices``: validate_record is the single validator, so an
    # invalid value is reported alongside every other violation instead of
    # aborting on the first one with a message that can drift from the schema.
    parser.add_argument("--basis", required=True, help="one of " + ", ".join(BASES))
    parser.add_argument("--decision", required=True, help="one of " + ", ".join(DECISIONS))
    parser.add_argument("--source-run-url", default=None, help="required when --basis measured")
    parser.add_argument(
        "--readiness-key",
        default=None,
        help="the production-readiness item this record proves (validation.production_readiness.REQUIRED_KEYS)",
    )
    parser.add_argument(
        "--control",
        action="append",
        default=[],
        help="repeatable; an L4 certification control this record attests (architecture/l4-certification.md)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    mapping = {
        "evidence_id": args.evidence_id,
        "scope": args.scope,
        "change": args.change,
        "claim": args.claim,
        "method": args.method,
        "result": args.result,
        "independence": args.independence,
        "artifacts": list(args.artifact),
        "approval": args.approval,
        "basis": args.basis,
        "decision": args.decision,
    }
    if args.source_run_url:
        mapping["source_run_url"] = args.source_run_url
    if args.readiness_key:
        mapping["readiness_key"] = args.readiness_key
    if args.control:
        mapping["controls"] = list(args.control)

    try:
        record = validate_record(mapping)
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return EXIT_INVALID_RECORD

    directory = Path(args.directory)
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"{record.evidence_id}.json"
    if target.exists():
        print(
            f"refusing to overwrite the existing evidence record {target}; "
            "records are immutable — write a new record that supersedes it",
            file=sys.stderr,
        )
        return EXIT_WOULD_OVERWRITE

    target.write_text(json.dumps(record.as_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"recorded {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
