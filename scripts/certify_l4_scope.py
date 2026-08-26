"""Build an L4 certification record for one scope, or say exactly why you cannot.

``architecture/l4-certification.md`` scopes certification to
``service + environment + runbook + blast-radius budget`` and lists nine
mandatory evidence items. This script is the only thing that produces the
``L4CertificationRecord`` that ``remediation.executor`` accepts as authority for
an L4 mutation, and it produces one only when every mandatory item is present.

What it refuses to do:

* count a rehearsal. ``scripts/run_l3_exercises.py --runner simulated`` grades
  its results ``rehearsal``; those are excluded before anything is counted;
* invent the two attestations no exercise can produce. ``security-review`` and
  ``independent-verification`` must exist as retained ``l4-promotion`` evidence
  records for the exact scope;
* write into ``docs/evidence/``. The evidence registry is written by
  ``scripts/record_evidence.py`` after a human review, never by a certifier;
* let the platform sign for itself. ``--issued-by`` must name a person or team.

Usage::

    python scripts/certify_l4_scope.py \\
        --exercises l3-exercises-<hash>.json --evidence-dir docs/evidence \\
        --service payments --environment prod --runbook aks.rollout.undo \\
        --blast-radius-budget 3 --policy-bundle-version eip-remediation-v1 \\
        --issued-by security@example.com

Exit codes: ``0`` certified, ``1`` not eligible (the missing list is printed),
``2`` the request itself is invalid.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Sequence

from remediation.catalog import default_catalog
from resilience.certification import (
    L4CertificationRecord,
    evaluate_l4_eligibility,
    material_inputs_hash_for,
)
from resilience.exercises import ExerciseKind, ExerciseResult
from resilience.scope import CertificationScope
from validation.evidence_records import load_registry


#: How long a certification stands before it must be reviewed again. This is a
#: review cadence, not evidence: an unexpired record proves only that nobody has
#: yet been asked to look again.
DEFAULT_VALID_DAYS = 90

#: Identities that are the platform, not a person. A certification signed by the
#: thing being certified is not a certification.
PLATFORM_IDENTITIES: frozenset[str] = frozenset({
    "eip",
    "platform",
    "ci",
    "bot",
    "automation",
    "github-actions",
    "github-actions[bot]",
    "engineering-intelligence-platform",
})

SELF_CERTIFICATION_NOTE = (
    "The platform cannot self-certify: --issued-by must name the person or team "
    "accountable for the promotion decision."
)


def _load_exercises(path: Path) -> tuple[ExerciseResult, ...]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    items: Any = payload.get("exercises") if isinstance(payload, dict) else payload
    if not isinstance(items, list):
        raise ValueError(f"{path}: expected a list of exercises, or an object with an 'exercises' list")
    results: list[ExerciseResult] = []
    for index, item in enumerate(items):
        try:
            results.append(ExerciseResult(
                kind=ExerciseKind(str(item["kind"])),
                passed=bool(item["passed"]),
                service=str(item["service"]),
                environment=str(item["environment"]),
                runbook_id=str(item["runbook_id"]),
                observed_blast_radius=int(item["observed_blast_radius"]),
                evidence_ref=str(item.get("evidence_ref", "")),
                # An entry that does not say what grade it is is a rehearsal:
                # the conservative reading is the only safe one here.
                evidence_grade=str(item.get("evidence_grade", "rehearsal")),
            ))
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError(f"{path}: exercise {index} is not a readable result: {error}") from error
    return tuple(results)


def _refuses_evidence_registry(output_dir: Path) -> bool:
    parts = [part.lower() for part in output_dir.resolve().parts]
    return any(
        parts[index] == "docs" and parts[index + 1] == "evidence"
        for index in range(len(parts) - 1)
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--exercises", type=Path, required=True, help="an l3-exercises-<hash>.json report")
    parser.add_argument("--evidence-dir", type=Path, required=True, help="the evidence registry directory")
    parser.add_argument("--service", required=True)
    parser.add_argument("--environment", required=True)
    parser.add_argument("--runbook", required=True)
    parser.add_argument("--blast-radius-budget", type=int, required=True)
    parser.add_argument(
        "--policy-bundle-version",
        required=True,
        help="the policy_revision the evaluator reports in the target environment",
    )
    parser.add_argument("--issued-by", required=True, help="the person or team signing this promotion")
    parser.add_argument("--valid-days", type=int, default=DEFAULT_VALID_DAYS)
    parser.add_argument("--output-dir", type=Path, default=Path("."))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if str(args.issued_by).strip().lower() in PLATFORM_IDENTITIES:
        print(SELF_CERTIFICATION_NOTE)
        return 2
    if not str(args.issued_by).strip():
        print(SELF_CERTIFICATION_NOTE)
        return 2
    if args.valid_days <= 0:
        print("--valid-days must be positive")
        return 2
    if _refuses_evidence_registry(args.output_dir):
        print(
            "refusing to write a certification into docs/evidence: the evidence "
            "registry records reviewed claims, not certifications derived from them"
        )
        return 2

    try:
        runbook = default_catalog().get(args.runbook)
    except KeyError as error:
        print(f"invalid scope: {error}")
        return 2
    if args.environment not in runbook.environments:
        print(f"invalid scope: runbook {runbook.id} is not permitted in {args.environment}")
        return 2
    try:
        scope = CertificationScope(
            service=args.service,
            environment=args.environment,
            runbook_id=runbook.id,
            blast_radius_budget=args.blast_radius_budget,
        )
    except ValueError as error:
        print(f"invalid scope: {error}")
        return 2

    try:
        exercises = _load_exercises(args.exercises)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"cannot read exercises: {error}")
        return 2
    try:
        records = load_registry(args.evidence_dir)
    except ValueError as error:
        print(f"cannot read the evidence registry: {error}")
        return 2

    now = datetime.now(timezone.utc)
    eligibility = evaluate_l4_eligibility(scope, exercises, records, now)
    print(
        f"L4 certification: scope={scope.evidence_scope()} budget={scope.blast_radius_budget} "
        f"counted_exercises={eligibility.counted_exercises} "
        f"rejected_rehearsals={eligibility.rejected_rehearsals}"
    )
    if not eligibility.eligible:
        print("NOT ELIGIBLE. Missing:")
        for item in eligibility.missing:
            print(f"  - {item}")
        return 1

    record = L4CertificationRecord(
        scope=scope,
        scope_hash=scope.scope_hash(),
        inputs_hash=material_inputs_hash_for(
            scope, runbook, policy_bundle_version=args.policy_bundle_version
        ),
        exercises_digest=eligibility.exercises_digest,
        issued_on=now.isoformat(),
        expires_on=(now + timedelta(days=args.valid_days)).isoformat(),
        issued_by=str(args.issued_by).strip(),
        evidence_ids=eligibility.evidence_ids,
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    output = args.output_dir / f"l4-certification-{scope.scope_hash()}.json"
    payload = {
        **record.as_dict(),
        "policy_bundle_version": args.policy_bundle_version,
        "note": (
            "This record authorises L4 execution for exactly this scope until it "
            "expires. Any material runbook, dependency, policy, verification-signal "
            "or blast-radius change invalidates it; see docs/L4-PROMOTION-RUNBOOK.md."
        ),
    }
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"certified until {record.expires_on}; wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
