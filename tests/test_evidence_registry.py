"""The evidence registry that docs/PRODUCTION-EVIDENCE.md specifies."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from validation.evidence_records import (
    BASES,
    DECISIONS,
    REQUIRED_FIELDS,
    EvidenceRecord,
    load_registry,
    registry_summary,
    validate_record,
)

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "docs" / "evidence"


def _record(**overrides):
    record = {
        "evidence_id": "2026-01-integration-proof-pilot",
        "scope": "acme/platform, integration, westeurope, internal, L0",
        "change": "sha=abc123 image=sha256:def digest, iac=v1.4.0, policy=bundle-9",
        "claim": "An unauthorized principal cannot retrieve protected evidence",
        "method": "Read-only integration probe against the integration environment",
        "result": "pass; 2/2 principals behaved as required at 2026-01-14T09:00Z",
        "independence": "SRE on-call reviewed the run; the verifier is not the deploying identity",
        "artifacts": ["https://example.invalid/run/1#sha256:aaa"],
        "approval": "owner=@service-owner reviewer=@sre expiry=2026-07-14",
        "basis": "measured",
        "decision": "real-data-pilot",
        "source_run_url": "https://example.invalid/run/1",
    }
    record.update(overrides)
    return {key: value for key, value in record.items() if value is not _ABSENT}


class _Absent:
    pass


_ABSENT = _Absent()


def test_the_nine_documented_fields_are_required():
    assert REQUIRED_FIELDS == (
        "evidence_id",
        "scope",
        "change",
        "claim",
        "method",
        "result",
        "independence",
        "artifacts",
        "approval",
    )


def test_a_complete_record_validates():
    record = validate_record(_record())

    assert isinstance(record, EvidenceRecord)
    assert record.evidence_id == "2026-01-integration-proof-pilot"
    assert record.artifacts == ("https://example.invalid/run/1#sha256:aaa",)


@pytest.mark.parametrize("field", REQUIRED_FIELDS + ("basis", "decision"))
def test_every_missing_field_is_named(field):
    with pytest.raises(ValueError) as error:
        validate_record(_record(**{field: _ABSENT}))

    assert field in str(error.value)


def test_every_violation_is_named_at_once():
    with pytest.raises(ValueError) as error:
        validate_record({"evidence_id": "ok-id"})

    message = str(error.value)
    for field in REQUIRED_FIELDS[1:] + ("basis", "decision"):
        assert field in message


def test_blank_values_are_violations():
    with pytest.raises(ValueError) as error:
        validate_record(_record(claim="   "))

    assert "claim" in str(error.value)


def test_artifacts_must_be_a_non_empty_list_of_strings():
    with pytest.raises(ValueError) as error:
        validate_record(_record(artifacts=[]))
    assert "artifacts" in str(error.value)

    with pytest.raises(ValueError) as error:
        validate_record(_record(artifacts="https://example.invalid/run/1"))
    assert "artifacts" in str(error.value)


def test_basis_is_restricted_to_the_three_declared_values():
    assert BASES == ("measured", "derived", "modeled")

    for basis in BASES:
        extra = {} if basis == "measured" else {"source_run_url": _ABSENT}
        assert validate_record(_record(basis=basis, **extra)).basis == basis

    with pytest.raises(ValueError) as error:
        validate_record(_record(basis="assumed"))
    assert "basis" in str(error.value)


def test_measured_records_require_a_source_run_url():
    with pytest.raises(ValueError) as error:
        validate_record(_record(basis="measured", source_run_url=_ABSENT))

    assert "source_run_url" in str(error.value)
    assert "measured" in str(error.value)


def test_decision_must_be_one_of_the_documented_decisions():
    assert "real-data-pilot" in DECISIONS

    with pytest.raises(ValueError) as error:
        validate_record(_record(decision="ship-it"))
    assert "decision" in str(error.value)


def test_evidence_id_must_be_a_safe_filename():
    for unsafe in ("../escape", "has space", "UPPER", "with/slash"):
        with pytest.raises(ValueError) as error:
            validate_record(_record(evidence_id=unsafe))
        assert "evidence_id" in str(error.value)


def test_unknown_fields_are_rejected():
    with pytest.raises(ValueError) as error:
        validate_record(_record(confidence="high"))

    assert "confidence" in str(error.value)


def test_load_registry_reads_every_json_file(tmp_path):
    first = _record()
    second = _record(evidence_id="2026-02-shadow-sample", decision="pr-guardian-advisory")
    for record in (first, second):
        (tmp_path / f"{record['evidence_id']}.json").write_text(json.dumps(record), encoding="utf-8")
    (tmp_path / "README.md").write_text("not a record\n", encoding="utf-8")

    records = load_registry(tmp_path)

    assert [record.evidence_id for record in records] == [
        "2026-01-integration-proof-pilot",
        "2026-02-shadow-sample",
    ]


def test_load_registry_names_the_offending_file(tmp_path):
    (tmp_path / "broken.json").write_text(json.dumps(_record(claim="")), encoding="utf-8")

    with pytest.raises(ValueError) as error:
        load_registry(tmp_path)

    assert "broken.json" in str(error.value)


def test_load_registry_requires_the_filename_to_match_the_evidence_id(tmp_path):
    (tmp_path / "other-name.json").write_text(json.dumps(_record()), encoding="utf-8")

    with pytest.raises(ValueError) as error:
        load_registry(tmp_path)

    assert "other-name.json" in str(error.value)


def test_load_registry_on_an_empty_directory_returns_nothing(tmp_path):
    assert load_registry(tmp_path) == ()


def test_load_registry_refuses_a_missing_directory(tmp_path):
    with pytest.raises(ValueError):
        load_registry(tmp_path / "nope")


def test_registry_summary_groups_by_decision_and_scope(tmp_path):
    records = tuple(
        validate_record(record)
        for record in (
            _record(),
            _record(evidence_id="b-record", decision="pr-guardian-advisory", basis="derived", source_run_url=_ABSENT),
            _record(evidence_id="c-record", decision="pr-guardian-advisory", scope="acme/other, integration, westeurope, internal, L1"),
        )
    )

    summary = registry_summary(records)

    assert summary["total"] == 3
    assert summary["by_decision"] == {"pr-guardian-advisory": 2, "real-data-pilot": 1}
    assert summary["by_basis"] == {"derived": 1, "measured": 2}
    assert summary["by_scope"]["acme/other, integration, westeurope, internal, L1"] == 1
    assert set(summary["decisions_without_records"]) == set(DECISIONS) - {
        "real-data-pilot",
        "pr-guardian-advisory",
    }


def test_registry_summary_of_an_empty_registry_reports_nothing_proven():
    summary = registry_summary(())

    assert summary["total"] == 0
    assert summary["by_decision"] == {}
    assert set(summary["decisions_without_records"]) == set(DECISIONS)


def test_the_shipped_registry_directory_validates():
    """The directory ships empty; an empty registry means nothing is proven."""

    records = load_registry(REGISTRY)

    assert registry_summary(records)["total"] == len(records)
