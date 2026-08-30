"""One validated correlation-id contract for inbound and durable workflows."""
from __future__ import annotations

import re
import uuid
from typing import NewType


CorrelationId = NewType("CorrelationId", str)
MAX_CORRELATION_ID_LENGTH = 128
_VALID_CORRELATION_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


def resolve_correlation_id(value: str | None = None) -> CorrelationId:
    """Return one safe correlation identifier, minting one only when absent.

    This accepts GitHub delivery ids and externally supplied request ids without
    letting whitespace, control characters, or unbounded header values flow to
    audit records, logs, or telemetry. Callers must preserve the returned value
    through every boundary; a workflow only mints an id for an internal caller
    that has no upstream correlation.
    """

    if value is None:
        return CorrelationId(str(uuid.uuid4()))
    if not isinstance(value, str):
        raise ValueError("correlation id must be a string")
    candidate = value.strip()
    if not candidate or len(candidate) > MAX_CORRELATION_ID_LENGTH:
        raise ValueError("invalid correlation id")
    if not _VALID_CORRELATION_ID.fullmatch(candidate):
        raise ValueError("invalid correlation id")
    return CorrelationId(candidate)
