"""The soak runner reads a telemetry export and refuses to round a short window up."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from scripts.run_soak import main
from validation.soak import load_samples


def write_window(path, *, hours: float, step_hours: float = 1.0, gap_at: int | None = None):
    start = datetime(2026, 8, 1, tzinfo=timezone.utc)
    lines = []
    index = 0
    elapsed = 0.0
    while elapsed <= hours:
        offset = elapsed + (6.0 if gap_at is not None and index > gap_at else 0.0)
        lines.append(json.dumps({
            "observed_at": (start + timedelta(hours=offset)).isoformat(),
            "passed": True,
            "evidence_ref": f"run://soak/{index}",
        }))
        index += 1
        elapsed += step_hours
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_an_empty_export_reports_nothing_and_exits_one(tmp_path, capsys):
    export = tmp_path / "soak.jsonl"
    export.write_text("", encoding="utf-8")
    assert main(["--input", str(export)]) == 1
    out = capsys.readouterr().out
    assert "continuous_hours=0.0" in out
    assert "qualifies=False" in out


def test_a_window_shorter_than_the_requirement_exits_one(tmp_path):
    export = tmp_path / "soak.jsonl"
    write_window(export, hours=100.0)
    assert main(["--input", str(export)]) == 1


def test_a_full_168_hour_window_exits_zero(tmp_path, capsys):
    export = tmp_path / "soak.jsonl"
    write_window(export, hours=200.0)
    assert main(["--input", str(export)]) == 0
    assert "qualifies=True" in capsys.readouterr().out


def test_a_gap_breaks_the_window_and_fails_the_requirement(tmp_path):
    export = tmp_path / "soak.jsonl"
    write_window(export, hours=200.0, gap_at=100)
    assert main(["--input", str(export)]) == 1


def test_the_requirement_is_the_documented_168_hours_by_default(tmp_path):
    export = tmp_path / "soak.jsonl"
    write_window(export, hours=169.0)
    assert main(["--input", str(export)]) == 0
    assert main(["--input", str(export), "--minimum-hours", "336"]) == 1


def test_a_malformed_record_is_named_and_never_silently_dropped(tmp_path, capsys):
    export = tmp_path / "soak.jsonl"
    export.write_text('{"observed_at": "2026-08-01T00:00:00+00:00", "passed": true}\n', encoding="utf-8")
    assert main(["--input", str(export)]) == 2
    assert "line 1" in capsys.readouterr().out


def test_naive_timestamps_are_rejected(tmp_path):
    export = tmp_path / "soak.jsonl"
    export.write_text(
        '{"observed_at": "2026-08-01T00:00:00", "passed": true, "evidence_ref": "r"}\n',
        encoding="utf-8",
    )
    assert main(["--input", str(export)]) == 2


def test_the_report_can_be_written_as_json(tmp_path):
    export = tmp_path / "soak.jsonl"
    write_window(export, hours=200.0)
    out = tmp_path / "soak-report.json"
    assert main(["--input", str(export), "--output", str(out)]) == 0
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["qualifies"] is True
    assert report["minimum_hours"] == 168.0


def test_samples_load_from_the_documented_jsonl_shape(tmp_path):
    export = tmp_path / "soak.jsonl"
    write_window(export, hours=3.0)
    samples = load_samples(export)
    assert len(samples) == 4
    assert samples[0].evidence_ref == "run://soak/0"
