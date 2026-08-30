from datetime import datetime, timezone

import pytest

from company_brain import RelationshipKind
from company_brain.model import BrainRelationship
from company_brain.serialization import (
    PayloadValidationError,
    parse_timestamp,
    payload_from_json,
    relationship_from_payload,
    relationship_payload,
)


def test_relationship_codec_round_trips_the_canonical_shape():
    relationship = BrainRelationship(
        source_id="service:payments",
        target_id="repository:acme/payments",
        kind=RelationshipKind.BELONGS_TO,
        evidence_ids=("evidence:adr-1",),
    )

    assert relationship_from_payload(relationship_payload(relationship)) == relationship


@pytest.mark.parametrize(
    "payload",
    (
        {"source_id": "service:payments", "target_id": "repository:acme/payments", "kind": "belongs_to", "evidence_ids": [1]},
        {"source_id": "service:payments", "target_id": "repository:acme/payments", "kind": "not-a-kind", "evidence_ids": []},
    ),
)
def test_relationship_codec_rejects_invalid_persisted_values(payload):
    with pytest.raises((PayloadValidationError, ValueError)):
        relationship_from_payload(payload)


def test_json_and_timestamp_codecs_reject_ambiguous_persisted_values():
    with pytest.raises(PayloadValidationError, match="must be a JSON object"):
        payload_from_json("[]", label="test")
    with pytest.raises(PayloadValidationError, match="must include a timezone"):
        parse_timestamp("2026-08-30T12:00:00", label="test.timestamp")

    assert parse_timestamp("2026-08-30T14:00:00+02:00", label="test.timestamp") == datetime(
        2026, 8, 30, 12, 0, tzinfo=timezone.utc
    )
