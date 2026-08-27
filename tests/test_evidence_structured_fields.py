"""Evidence records carry structured fields readers key on; nobody parses ``claim``."""
from __future__ import annotations

import json

import pytest

from resilience.certification import ATTESTED_CONTROLS, L4_EVIDENCE_DECISION, _attests
from resilience.scope import CertificationScope
from scripts.record_evidence import main as record_main
from validation.evidence_records import validate_record
from validation.production_readiness import REQUIRED_KEYS, readiness_evidence_from_record


def base_record(**overrides):
    record = {
        "evidence_id": "2026-09-soak",
        "scope": "payments/prod/aks.rollout.undo",
        "change": "sha=abc image=sha256:def policy=eip-remediation-v1",
        "claim": "The soak window held for 168 hours",
        "method": "observed operational window",
        "result": "pass; 168h; limitations: single region",
        "independence": "SRE, not the deploying identity",
        "artifacts": ["https://example.invalid/run/1"],
        "approval": "owner=@a reviewer=@b expiry=2027-01-01",
        "basis": "measured",
        "decision": "l3-remediation-pilot",
        "source_run_url": "https://example.invalid/run/1",
    }
    record.update(overrides)
    return record


def test_readiness_key_must_name_a_required_item():
    with pytest.raises(ValueError, match="readiness_key: must be one of"):
        validate_record(base_record(readiness_key="something-else"))
    record = validate_record(base_record(readiness_key="production-like-soak"))
    assert record.readiness_key == "production-like-soak"
    assert "production-like-soak" in REQUIRED_KEYS


def test_controls_must_be_a_list_of_control_names():
    with pytest.raises(ValueError, match="controls: must be a list"):
        validate_record(base_record(controls="security-review-complete"))
    with pytest.raises(ValueError, match="controls: every entry"):
        validate_record(base_record(controls=["security-review-complete", ""]))
    record = validate_record(base_record(controls=[" verification-independent ", "verification-independent"]))
    assert record.controls == ("verification-independent",)


def test_structured_fields_round_trip_through_as_dict():
    record = validate_record(base_record(readiness_key="audit-export", controls=["security-review-complete"]))
    payload = record.as_dict()
    assert payload["readiness_key"] == "audit-export"
    assert payload["controls"] == ["security-review-complete"]
    plain = validate_record(base_record()).as_dict()
    assert "readiness_key" not in plain and "controls" not in plain


def test_passed_reads_only_the_first_segment_of_result():
    assert validate_record(base_record(result="pass; 168h")).passed is True
    assert validate_record(base_record(result="PASS")).passed is True
    assert validate_record(base_record(result="passed with caveats")).passed is False
    assert validate_record(base_record(result="fail; 100h")).passed is False


def test_the_readiness_reader_uses_the_structured_key_and_ignores_prose():
    structured = validate_record(base_record(readiness_key="production-like-soak")).as_dict()
    item = readiness_evidence_from_record(structured)
    assert item is not None and item.key == "production-like-soak" and item.passed is True
    prose_only = validate_record(base_record(claim="production-like-soak")).as_dict()
    assert readiness_evidence_from_record(prose_only) is None


def test_attestation_is_by_control_membership_not_claim_text():
    scope = CertificationScope(service="payments", environment="prod", runbook_id="aks.rollout.undo", blast_radius_budget=5)
    control = ATTESTED_CONTROLS[0]
    negated_claim = validate_record(base_record(
        decision=L4_EVIDENCE_DECISION,
        scope=scope.evidence_scope(),
        claim=f"{control} was NOT achieved for this scope",
    ))
    assert _attests(negated_claim, scope=scope, control=control) is False
    attested = validate_record(base_record(
        decision=L4_EVIDENCE_DECISION,
        scope=scope.evidence_scope(),
        claim="reviewed",
        controls=[control],
    ))
    assert _attests(attested, scope=scope, control=control) is True


def test_the_cli_writes_the_structured_fields(tmp_path):
    code = record_main([
        "--directory", str(tmp_path),
        "--evidence-id", "2026-09-soak",
        "--scope", "payments/prod/aks.rollout.undo",
        "--change", "sha=abc",
        "--claim", "soak held",
        "--readiness-key", "production-like-soak",
        "--control", "security-review-complete",
        "--control", "verification-independent",
        "--method", "observed window",
        "--result", "pass; 168h",
        "--independence", "SRE",
        "--artifact", "https://example.invalid/run/1",
        "--approval", "owner=@a",
        "--basis", "measured",
        "--decision", "l3-remediation-pilot",
        "--source-run-url", "https://example.invalid/run/1",
    ])
    assert code == 0
    written = json.loads((tmp_path / "2026-09-soak.json").read_text(encoding="utf-8"))
    assert written["readiness_key"] == "production-like-soak"
    assert written["controls"] == ["security-review-complete", "verification-independent"]
