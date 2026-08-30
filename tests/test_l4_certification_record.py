"""The record the execution path checks, and the four ways it stops matching."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from resilience.certification import L4CertificationRecord, certification_refusal
from resilience.scope import CertificationScope


NOW = datetime(2026, 8, 26, tzinfo=timezone.utc)
SCOPE = CertificationScope(
    service="payments", environment="prod", runbook_id="aks.rollout.undo", blast_radius_budget=3
)


def record(**overrides) -> L4CertificationRecord:
    fields = {
        "scope": SCOPE,
        "scope_hash": SCOPE.scope_hash(),
        "inputs_hash": "a" * 64,
        "exercises_digest": "sha256:deadbeef",
        "issued_on": "2026-08-01T00:00:00+00:00",
        "expires_on": "2026-11-01T00:00:00+00:00",
        "issued_by": "security@example.invalid",
        "evidence_ids": ("l4-security-review",),
    }
    fields.update(overrides)
    return L4CertificationRecord(**fields)


def refusal(candidate, **kwargs):
    return certification_refusal(
        candidate, scope_hash=kwargs.get("scope_hash", SCOPE.scope_hash()),
        inputs_hash=kwargs.get("inputs_hash", "a" * 64), now=NOW,
    )


def test_a_matching_unexpired_record_is_not_refused():
    assert refusal(record()) is None


def test_no_record_is_refused():
    assert "no certification record" in refusal(None)


def test_an_expired_record_is_refused():
    assert "expired" in refusal(record(expires_on="2026-08-25T00:00:00+00:00"))


def test_an_unreadable_expiry_is_refused():
    assert "expires_on" in refusal(record(expires_on="whenever"))


def test_a_naive_expiry_is_read_as_utc_and_still_refused_when_past():
    assert "expired" in refusal(record(expires_on="2026-08-25T00:00:00"))


def test_a_record_for_another_scope_is_refused():
    assert "scope" in refusal(record(scope_hash="b" * 64))


def test_changed_material_inputs_are_refused():
    message = refusal(record(inputs_hash="c" * 64))
    assert "material inputs" in message and "recertification" in message


def test_every_refusal_names_the_check():
    for candidate in (None, record(scope_hash="b" * 64), record(inputs_hash="c" * 64)):
        assert refusal(candidate).startswith("l4-certification:")


def test_a_record_round_trips_through_json():
    original = record()
    assert L4CertificationRecord.from_dict(original.as_dict()) == original


@pytest.mark.parametrize(
    ("payload", "message"),
    (
        ({"scope": {}}, "missing service"),
        ({**record().as_dict(), "scope": "not-an-object"}, "scope must be an object"),
        ({**record().as_dict(), "scope": {**SCOPE.canonical(), "blast_radius_budget": "3"}}, "positive integer"),
        ({**record().as_dict(), "evidence_ids": "not-a-list"}, "list of non-blank strings"),
    ),
)
def test_a_malformed_persisted_record_fails_closed(payload, message):
    with pytest.raises(ValueError, match=message):
        L4CertificationRecord.from_dict(payload)
