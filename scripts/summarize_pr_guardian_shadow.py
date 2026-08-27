from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable, Mapping

from feedback.pr_guardian_shadow import build_shadow_report


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize exported PR Guardian shadow outcomes")
    parser.add_argument("inputs", nargs="+", type=Path, help="JSON/JSONL files or directories containing outcome exports")
    parser.add_argument("--output", type=Path, default=Path("pr-guardian-shadow-report.json"))
    args = parser.parse_args()
    outcomes = list(_load_inputs(args.inputs))
    report = build_shadow_report(outcomes)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    readiness = report["promotion_readiness"]
    print(
        f"PR Guardian shadow report: records={report['sample']['closure_records']} "
        f"decision={readiness['decision']} blocking_authorized={readiness['blocking_authorized']} "
        f"next_review={readiness['next_review']} output={args.output}"
    )
    return 0


def _load_inputs(paths: Iterable[Path]) -> Iterable[Mapping[str, object]]:
    files: list[Path] = []
    for path in paths:
        if path.is_dir():
            files.extend(sorted(item for item in path.rglob("*") if item.suffix in {".json", ".jsonl"}))
        else:
            files.append(path)
    for path in sorted(files):
        if path.suffix == ".jsonl":
            for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
                if line.strip():
                    yield _object(json.loads(line), f"{path}:{line_number}")
            continue
        loaded = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(loaded, list):
            for index, item in enumerate(loaded):
                yield _object(item, f"{path}[{index}]")
        else:
            yield _object(loaded, str(path))


def _object(value: object, origin: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{origin} must contain a JSON object")
    return value


if __name__ == "__main__":
    raise SystemExit(main())
