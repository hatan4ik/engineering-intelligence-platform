"""The readiness runner names every missing gate and never invents a passing one."""
from __future__ import annotations

import json

from scripts.production_readiness_report import main
from validation.production_readiness import REQUIRED_KEYS, load_readiness_evidence


def write_record(directory, key, *, passed=True, evidence_ref="run://evidence/1"):
    """A registry-shaped record: the reader keys on ``readiness_key`` and the
    first ``;``-segment of ``result``, never on the free-text ``claim``."""
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{key}.json").write_text(
        json.dumps({
            "evidence_id": f"sha256:{key}",
            "claim": f"{key} was exercised in prod-like conditions",
            "readiness_key": key,
            "basis": "measured",
            "method": "drill",
            "result": "pass; 1/1 exercised" if passed else "fail; 0/1 exercised",
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


def test_the_loader_never_parses_the_free_text_claim(tmp_path):
    """A claim that happens to equal a key is not a readiness_key."""
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    (evidence / "prose.json").write_text(
        json.dumps({
            "evidence_id": "prose",
            "claim": "audit-export",
            "result": "pass",
            "artifacts": ["run://evidence/1"],
        }),
        encoding="utf-8",
    )
    loaded = load_readiness_evidence(evidence)
    assert loaded.evidence == ()
    assert len(loaded.ignored) == 1


def test_only_an_exact_pass_verdict_counts(tmp_path):
    evidence = tmp_path / "evidence"
    for name, result in (("a", "passed with caveats"), ("b", "PASS ; but see limits"), ("c", "success")):
        evidence.mkdir(exist_ok=True)
        (evidence / f"{name}.json").write_text(
            json.dumps({
                "evidence_id": name,
                "readiness_key": "audit-export",
                "result": result,
                "artifacts": ["run://evidence/1"],
            }),
            encoding="utf-8",
        )
    verdicts = {item.evidence_ref and path.name: item.passed for path, item in zip(sorted(evidence.glob("*.json")), load_readiness_evidence(evidence).evidence)}
    assert verdicts == {"a.json": False, "b.json": True, "c.json": False}
