"""Evaluate production readiness from a retained evidence registry.

The registry is a directory of JSON evidence records
(``docs/PRODUCTION-EVIDENCE.md``). This runner reads it, maps each record onto
the readiness key it claims to prove, and evaluates the fail-closed gate in
``validation/production_readiness.py``.

It never invents a passing gate. An empty or absent directory means every
required key is missing, which is what "not proven" looks like. Records that
name no required key are reported as ignored rather than dropped in silence.

Usage::

    python scripts/production_readiness_report.py --dir docs/evidence
"""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from validation.production_readiness import (
    REQUIRED_KEYS,
    evaluate_production_readiness,
    load_readiness_evidence,
)
from validation.soak import SoakExportError, evaluate_soak, load_samples


MINIMUM_SOAK_HOURS = 168.0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Report production readiness from an evidence directory")
    parser.add_argument("--dir", type=Path, default=Path("docs/evidence"))
    parser.add_argument("--soak-samples", type=Path, default=None, help="optional JSONL soak export")
    parser.add_argument("--minimum-soak-hours", type=float, default=MINIMUM_SOAK_HOURS)
    parser.add_argument("--metrics", type=Path, default=None, help="optional JSON of observed metrics")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args(argv)

    loaded = load_readiness_evidence(args.dir)

    soak_report = None
    if args.soak_samples is not None:
        try:
            soak_report = evaluate_soak(
                load_samples(args.soak_samples), minimum_hours=args.minimum_soak_hours
            )
        except (OSError, SoakExportError) as exc:
            print(f"soak export could not be read: {exc}")
            return 2

    metrics = {}
    if args.metrics is not None:
        try:
            metrics = json.loads(args.metrics.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"metrics file could not be read: {exc}")
            return 2

    report = evaluate_production_readiness(
        loaded.evidence,
        soak_report=soak_report,
        minimum_soak_hours=args.minimum_soak_hours,
        observed_metrics=metrics,
    )

    print(
        f"production readiness: ready={report.ready} score={report.score} "
        f"evidence_files={loaded.files_read} evidence_records={len(loaded.evidence)} "
        f"required_keys={len(REQUIRED_KEYS)}"
    )
    print("passed:")
    for key in report.passed:
        print(f"  - {key}")
    print("missing:")
    for key in report.missing:
        print(f"  - {key}")
    if loaded.ignored:
        print("ignored records:")
        for item in loaded.ignored:
            print(f"  - {item}")
    if not report.ready:
        print("Not production ready. The absence of an evidence record means not proven.")

    if args.output is not None:
        payload = {
            **asdict(report),
            "passed": list(report.passed),
            "missing": list(report.missing),
            "evidence_refs": list(report.evidence_refs),
            "evidence_files": loaded.files_read,
            "ignored_records": list(loaded.ignored),
            "source": str(args.dir),
        }
        args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    return 0 if report.ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
