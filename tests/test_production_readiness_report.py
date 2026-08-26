"""The readiness runner names every missing gate and never invents a passing one."""
from __future__ import annotations

import json

from scripts.production_readiness_report import main
from validation.production_readiness import REQUIRED_KEYS, load_readiness_evidence


def write_record(directory, key, *, passed=True, evidence_ref="run://evidence/1"):
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{key}.json").write_text(
        json.dumps({
            "evidence_id": f"sha256:{key}",
            "claim": key,
            "basis": "measured",
            "method": "drill",
            "result": {"passed": passed},
            "artifacts": [evidence_ref],
        }),
        encoding="utf-8",
    )


def test_an_empty_directory_reports_every_required_key_missing(tmp_path, capsys):
    (tmp_path / "evidence").mkdir()
    assert main(["--dir", str(tmp_path / "evidence")]) == 1
    out = capsys.readouterr().out
    for key in REQUIRED_KEYS:
        assert key in out
    assert "ready=False" in out


def test_a_missing_directory_is_treated_as_no_evidence(tmp_path, capsys):
    assert main(["--dir", str(tmp_path / "absent")]) == 1
    assert "ready=False" in capsys.readouterr().out


def test_a_partial_directory_names_only_the_keys_that_are_still_missing(tmp_path, capsys):
    evidence = tmp_path / "evidence"
    write_record(evidence, "audit-export")
    write_record(evidence, "rollback-drill")
    assert main(["--dir", str(evidence)]) == 1
    out = capsys.readouterr().out
    assert "kill-switch-drill" in out
    missing_block = out.split("missing:", 1)[1]
    assert "- audit-export" not in missing_block
    assert "- rollback-drill" not in missing_block


def test_a_failed_record_counts_as_missing(tmp_path, capsys):
    evidence = tmp_path / "evidence"
    write_record(evidence, "audit-export", passed=False)
    assert main(["--dir", str(evidence)]) == 1
    assert "- audit-export" in capsys.readouterr().out.split("missing:", 1)[1]


def test_a_record_without_an_evidence_reference_counts_as_missing(tmp_path, capsys):
    evidence = tmp_path / "evidence"
    write_record(evidence, "audit-export", evidence_ref="")
    assert main(["--dir", str(evidence)]) == 1
    assert "- audit-export" in capsys.readouterr().out.split("missing:", 1)[1]


def test_records_that_do_not_name_a_required_key_are_reported_not_silently_dropped(tmp_path, capsys):
    evidence = tmp_path / "evidence"
    write_record(evidence, "some-other-claim")
    assert main(["--dir", str(evidence)]) == 1
    assert "ignored" in capsys.readouterr().out


def test_a_full_evidence_set_still_needs_soak_and_l3_evidence(tmp_path, capsys):
    evidence = tmp_path / "evidence"
    for key in REQUIRED_KEYS:
        write_record(evidence, key)
    assert main(["--dir", str(evidence)]) == 1
    out = capsys.readouterr().out
    assert "l3-certification-evidence" in out
    assert "soak-hours<168" in out


def test_the_loader_reads_the_registry_shape(tmp_path):
    evidence = tmp_path / "evidence"
    write_record(evidence, "audit-export")
    loaded = load_readiness_evidence(evidence)
    assert [item.key for item in loaded.evidence] == ["audit-export"]
    assert loaded.files_read == 1
    assert loaded.ignored == ()
