"""Evaluate a continuous-operation soak window from a telemetry export.

The 168-hour requirement comes from ``docs/PRODUCTION-PROOF-PLAN.md``: "at least
168 continuous hours of production-like operation before readiness review". The
window is *continuous* -- a failed sample, a sample with no evidence reference,
or a gap wider than ``--maximum-gap-hours`` ends it and a new one starts.

The export shape is documented in ``validation/soak.py``. This runner reads it,
prints the report, and exits 1 when the longest continuous window is shorter
than the requirement. It never rounds a short window up and never fills a gap.

Usage::

    python scripts/run_soak.py --input soak-telemetry.jsonl
"""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from validation.soak import SoakExportError, evaluate_soak, load_samples


REQUIRED_HOURS = 168.0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate a production-like soak window")
    parser.add_argument("--input", required=True, type=Path, help="JSONL telemetry export")
    parser.add_argument("--minimum-hours", type=float, default=REQUIRED_HOURS)
    parser.add_argument("--maximum-gap-hours", type=float, default=2.0)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args(argv)

    try:
        samples = load_samples(args.input)
    except (OSError, SoakExportError) as exc:
        print(f"soak export could not be read: {exc}")
        return 2

    report = evaluate_soak(
        samples,
        minimum_hours=args.minimum_hours,
        maximum_gap_hours=args.maximum_gap_hours,
    )
    print(
        f"soak: continuous_hours={report.continuous_hours} "
        f"minimum_hours={args.minimum_hours:g} qualifies={report.qualifies} "
        f"samples={report.sample_count} passed={report.passed_samples} "
        f"failed={report.failed_samples} evidence_refs={len(report.evidence_refs)}"
    )
    if not report.qualifies:
        print(
            f"the longest continuous window is {report.continuous_hours}h, "
            f"short of the required {args.minimum_hours:g}h"
        )

    if args.output is not None:
        payload = {
            **asdict(report),
            "evidence_refs": list(report.evidence_refs),
            "minimum_hours": args.minimum_hours,
            "maximum_gap_hours": args.maximum_gap_hours,
            "source": str(args.input),
        }
        args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    return 0 if report.qualifies else 1


if __name__ == "__main__":
    raise SystemExit(main())
