"""Typed, fail-closed codecs shared by Company Brain persistence adapters.

SQLite stores JSON text, which is untrusted at the persistence boundary even
when this process originally wrote it.  Keep decoding here so every adapter
uses the same validation and timestamp normalization rules.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Mapping, Protocol

from .model import BrainRelationship, RelationshipKind


class PayloadValidationError(ValueError):
    """Raised when a persisted Company Brain payload has an invalid shape."""


class ProvenanceLike(Protocol):
    """The stable provenance fields that Company Brain codecs persist."""

    @property
    def source_system(self) -> str: ...

    @property
    def source_record_id(self) -> str: ...

    @property
    def source_revision(self) -> str: ...

    @property
    def observed_at(self) -> datetime: ...

    @property
    def event_id(self) -> str | None: ...


@dataclass(frozen=True)
class ProvenanceFields:
    """Validated provenance values ready for the domain constructor."""

    source_system: str
    source_record_id: str
    source_revision: str
    observed_at: datetime
    event_id: str | None


Payload = Mapping[str, object]


def payload_from_json(serialized: str, *, label: str) -> dict[str, object]:
    """Decode a JSON object, rejecting non-object roots and non-string keys."""

    try:
        decoded: object = json.loads(serialized)
    except json.JSONDecodeError as error:
        raise PayloadValidationError(f"{label} is not valid JSON") from error
    if not isinstance(decoded, dict):
        raise PayloadValidationError(f"{label} must be a JSON object")
    result: dict[str, object] = {}
    for key, value in decoded.items():
        if not isinstance(key, str):
            raise PayloadValidationError(f"{label} contains a non-string key")
        result[key] = value
    return result


def payload_from_value(value: object, *, label: str) -> dict[str, object]:
    """Narrow a decoded nested JSON value to a string-keyed object."""

    if not isinstance(value, dict):
        raise PayloadValidationError(f"{label} must be an object")
    result: dict[str, object] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            raise PayloadValidationError(f"{label} contains a non-string key")
        result[key] = item
    return result


def required_text(payload: Payload, field: str, *, label: str) -> str:
    """Read a required non-empty string field from an untrusted payload."""

    value = payload.get(field)
    if not isinstance(value, str) or not value:
        raise PayloadValidationError(f"{label}.{field} must be a non-empty string")
    return value


def optional_text(payload: Payload, field: str, *, label: str) -> str | None:
    """Read an optional string field without coercing arbitrary values."""

    value = payload.get(field)
    if value is None:
        return None
    if not isinstance(value, str):
        raise PayloadValidationError(f"{label}.{field} must be a string when supplied")
    return value


def text_sequence(payload: Payload, field: str, *, label: str, default: tuple[str, ...] = ()) -> tuple[str, ...]:
    """Read a JSON list of strings, preserving an explicit backwards-compatible default."""

    value = payload.get(field)
    if value is None:
        return default
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise PayloadValidationError(f"{label}.{field} must be a list of strings")
    return tuple(value)


def required_text_sequence(payload: Payload, field: str, *, label: str) -> tuple[str, ...]:
    """Read a required JSON list of strings."""

    if field not in payload:
        raise PayloadValidationError(f"{label}.{field} is required")
    return text_sequence(payload, field, label=label)


def required_object_sequence(payload: Payload, field: str, *, label: str) -> tuple[object, ...]:
    """Read a required JSON list while preserving element validation to its codec."""

    value = payload.get(field)
    if not isinstance(value, list):
        raise PayloadValidationError(f"{label}.{field} must be a list")
    return tuple(value)


def text_pairs(payload: Payload, field: str, *, label: str) -> tuple[tuple[str, str], ...]:
    """Read a JSON list of two-string attribute pairs."""

    value = payload.get(field, [])
    if not isinstance(value, list):
        raise PayloadValidationError(f"{label}.{field} must be a list")
    pairs: list[tuple[str, str]] = []
    for item in value:
        if (
            not isinstance(item, list)
            or len(item) != 2
            or not isinstance(item[0], str)
            or not isinstance(item[1], str)
        ):
            raise PayloadValidationError(f"{label}.{field} must contain two-string pairs")
        pairs.append((item[0], item[1]))
    return tuple(pairs)


def relationship_payload(relationship: BrainRelationship) -> dict[str, object]:
    """Serialize a relationship using the canonical Company Brain shape."""

    return {
        "source_id": relationship.source_id,
        "target_id": relationship.target_id,
        "kind": relationship.kind.value,
        "evidence_ids": list(relationship.evidence_ids),
    }


def relationship_from_payload(payload: Payload) -> BrainRelationship:
    """Deserialize a relationship without silently coercing malformed values."""

    return BrainRelationship(
        source_id=required_text(payload, "source_id", label="relationship"),
        target_id=required_text(payload, "target_id", label="relationship"),
        kind=RelationshipKind(required_text(payload, "kind", label="relationship")),
        evidence_ids=text_sequence(payload, "evidence_ids", label="relationship"),
    )


def provenance_payload(provenance: ProvenanceLike) -> dict[str, object]:
    """Serialize provenance with an explicit UTC timestamp."""

    return {
        "source_system": provenance.source_system,
        "source_record_id": provenance.source_record_id,
        "source_revision": provenance.source_revision,
        "observed_at": utc_timestamp(provenance.observed_at, label="provenance observed_at").isoformat(),
        "event_id": provenance.event_id,
    }


def provenance_fields(payload: Payload) -> ProvenanceFields:
    """Validate the canonical provenance payload for a domain constructor."""

    return ProvenanceFields(
        source_system=required_text(payload, "source_system", label="provenance"),
        source_record_id=required_text(payload, "source_record_id", label="provenance"),
        source_revision=required_text(payload, "source_revision", label="provenance"),
        observed_at=parse_timestamp(payload.get("observed_at"), label="provenance.observed_at"),
        event_id=optional_text(payload, "event_id", label="provenance"),
    )


def utc_timestamp(value: datetime, *, label: str) -> datetime:
    """Require a timezone-aware timestamp and normalize it to UTC."""

    if value.tzinfo is None or value.utcoffset() is None:
        raise PayloadValidationError(f"{label} must include a timezone")
    return value.astimezone(timezone.utc)


def parse_timestamp(value: object, *, label: str) -> datetime:
    """Parse an ISO timestamp and reject naive or non-string values."""

    if not isinstance(value, str):
        raise PayloadValidationError(f"{label} must be an ISO timestamp string")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise PayloadValidationError(f"{label} must be an ISO timestamp string") from error
    return utc_timestamp(parsed, label=label)
