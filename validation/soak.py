"""Continuous-operation soak evaluation over a timestamped telemetry export.

The export is JSONL: one JSON object per line, one object per observation, in
any order. Each object carries exactly the :class:`SoakSample` fields::

    {"observed_at": "2026-08-01T00:00:00+00:00", "passed": true,
     "evidence_ref": "run://soak/0"}

``observed_at`` must be ISO-8601 with an explicit timezone (a trailing ``Z`` is
accepted); a naive timestamp is rejected rather than assumed to be UTC.
``passed`` is the observation's own verdict, and ``evidence_ref`` points at the
retained artifact for it -- a sample with no reference cannot extend a window,
because an unreferenced claim is not evidence.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from collections.abc import Mapping as AbcMapping
from pathlib import Path
from typing import Mapping


@dataclass(frozen=True)
class SoakSample:
    observed_at: str
    passed: bool
    evidence_ref: str

    def timestamp(self) -> datetime:
        value = self.observed_at.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            raise ValueError("soak sample timestamp must be timezone-aware")
        return parsed.astimezone(timezone.utc)


@dataclass(frozen=True)
class SoakReport:
    continuous_hours: float
    sample_count: int
    passed_samples: int
    failed_samples: int
    evidence_refs: tuple[str, ...]
    qualifies: bool


def evaluate_soak(
    samples: tuple[SoakSample, ...],
    *,
    minimum_hours: float = 168.0,
    maximum_gap_hours: float = 2.0,
) -> SoakReport:
    if minimum_hours <= 0 or maximum_gap_hours <= 0:
        raise ValueError("soak thresholds must be positive")
    if not samples:
        return SoakReport(0.0, 0, 0, 0, (), False)

    ordered = tuple(sorted(samples, key=lambda sample: sample.timestamp()))
    start: datetime | None = None
    last: datetime | None = None
    best_hours = 0.0
    current_refs: list[str] = []
    best_refs: tuple[str, ...] = ()

    for sample in ordered:
        ts = sample.timestamp()
        valid = sample.passed and bool(sample.evidence_ref.strip())
        if not valid:
            if start is not None and last is not None:
                duration = (last - start).total_seconds() / 3600.0
                if duration > best_hours:
                    best_hours = duration
                    best_refs = tuple(current_refs)
            start = last = None
            current_refs = []
            continue

        if last is not None:
            gap = (ts - last).total_seconds() / 3600.0
            if gap > maximum_gap_hours:
                duration = (last - start).total_seconds() / 3600.0 if start else 0.0
                if duration > best_hours:
                    best_hours = duration
                    best_refs = tuple(current_refs)
                start = ts
                current_refs = [sample.evidence_ref]
            else:
                current_refs.append(sample.evidence_ref)
        else:
            start = ts
            current_refs = [sample.evidence_ref]
        last = ts

    if start is not None and last is not None:
        duration = (last - start).total_seconds() / 3600.0
        if duration > best_hours:
            best_hours = duration
            best_refs = tuple(current_refs)

    passed = sum(sample.passed and bool(sample.evidence_ref.strip()) for sample in ordered)
    failed = len(ordered) - passed
    return SoakReport(
        continuous_hours=round(best_hours, 3),
        sample_count=len(ordered),
        passed_samples=passed,
        failed_samples=failed,
        evidence_refs=tuple(dict.fromkeys(best_refs)),
        qualifies=best_hours >= minimum_hours,
    )


class SoakExportError(ValueError):
    """A telemetry export line could not be read as a soak sample."""


def parse_sample(record: Mapping[str, object]) -> SoakSample:
    """Build one sample from an export record, naming what is wrong if it is."""
    missing = [field for field in ("observed_at", "passed", "evidence_ref") if field not in record]
    if missing:
        raise SoakExportError("soak sample is missing: " + ", ".join(missing))
    if not isinstance(record["passed"], bool):
        raise SoakExportError("soak sample 'passed' must be a JSON boolean")
    sample = SoakSample(
        observed_at=str(record["observed_at"]),
        passed=bool(record["passed"]),
        evidence_ref=str(record["evidence_ref"]),
    )
    try:
        sample.timestamp()
    except ValueError as exc:
        raise SoakExportError(f"soak sample timestamp is unusable: {exc}") from exc
    return sample


def load_samples(path: str | Path) -> tuple[SoakSample, ...]:
    """Read a JSONL telemetry export. Every unreadable line is named."""
    samples: list[SoakSample] = []
    text = Path(path).read_text(encoding="utf-8")
    for number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise SoakExportError(f"line {number} is not valid JSON: {exc}") from exc
        if not isinstance(record, AbcMapping):
            raise SoakExportError(f"line {number} must be a JSON object")
        try:
            samples.append(parse_sample(record))
        except SoakExportError as exc:
            raise SoakExportError(f"line {number}: {exc}") from exc
    return tuple(samples)
