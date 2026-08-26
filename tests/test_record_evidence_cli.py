"""The evidence-recording CLI refuses anything it cannot stand behind."""
from __future__ import annotations

import json

from scripts.record_evidence import main
from validation.evidence_records import load_registry


def _argv(directory, **overrides):
    values = {
        "--directory": str(directory),
        "--evidence-id": "2026-01-integration-proof-pilot",
        "--scope": "acme/platform, integration, westeurope, internal, L0",
        "--change": "sha=abc123 image=sha256:def iac=v1.4.0 policy=bundle-9",
        "--claim": "An unauthorized principal cannot retrieve protected evidence",
        "--method": "Read-only integration probe",
        "--result": "pass; 2/2 principals behaved as required",
        "--independence": "SRE reviewed; verifier is not the deploying identity",
        "--approval": "owner=@service-owner reviewer=@sre expiry=2026-07-14",
        "--basis": "measured",
        "--decision": "real-data-pilot",
        "--source-run-url": "https://example.invalid/run/1",
    }
    values.update(overrides)
    argv = [item for key, value in values.items() if value is not None for item in (key, value)]
    return argv + ["--artifact", "https://example.invalid/run/1#sha256:aaa"]


def test_writes_one_validated_record(tmp_path, capsys):
    assert main(_argv(tmp_path)) == 0

    written = tmp_path / "2026-01-integration-proof-pilot.json"
    payload = json.loads(written.read_text(encoding="utf-8"))
    assert payload["basis"] == "measured"
    assert payload["artifacts"] == ["https://example.invalid/run/1#sha256:aaa"]
    assert [record.evidence_id for record in load_registry(tmp_path)] == [
        "2026-01-integration-proof-pilot"
    ]
    assert str(written) in capsys.readouterr().out


def test_refuses_to_overwrite_an_existing_record(tmp_path, capsys):
    assert main(_argv(tmp_path)) == 0
    original = (tmp_path / "2026-01-integration-proof-pilot.json").read_text(encoding="utf-8")

    code = main(_argv(tmp_path, **{"--result": "pass; rewritten"}))

    assert code == 3
    assert "refus" in capsys.readouterr().err.lower()
    assert (tmp_path / "2026-01-integration-proof-pilot.json").read_text(encoding="utf-8") == original


def test_refuses_a_measured_record_without_a_source_run_url(tmp_path, capsys):
    code = main(_argv(tmp_path, **{"--source-run-url": None}))

    assert code == 2
    assert "source_run_url" in capsys.readouterr().err
    assert list(tmp_path.glob("*.json")) == []


def test_a_modeled_record_needs_no_source_run_url(tmp_path):
    argv = _argv(tmp_path, **{"--basis": "modeled", "--source-run-url": None})

    assert main(argv) == 0


def test_reports_every_validation_violation(tmp_path, capsys):
    code = main(_argv(tmp_path, **{"--claim": "   ", "--decision": "ship-it"}))

    assert code == 2
    error = capsys.readouterr().err
    assert "claim" in error
    assert "decision" in error
