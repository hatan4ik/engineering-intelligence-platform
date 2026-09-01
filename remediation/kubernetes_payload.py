"""Narrow untrusted Kubernetes JSON before it can influence a control loop."""

from __future__ import annotations

import json
from collections.abc import Mapping


KubernetesObject = Mapping[str, object]


class KubernetesPayloadError(RuntimeError):
    """A Kubernetes API response did not have the shape a safety check needs."""


def parse_object(raw: str, *, context: str) -> KubernetesObject:
    """Parse one Kubernetes API object and reject malformed shapes.

    A remediation decision must not treat malformed nested JSON as an empty,
    apparently safe object. Callers either receive a narrow mapping or a
    failure they can escalate.
    """

    try:
        payload: object = json.loads(raw)
    except json.JSONDecodeError as error:
        raise KubernetesPayloadError(
            f"Kubernetes {context} response is not JSON"
        ) from error
    if not isinstance(payload, Mapping):
        raise KubernetesPayloadError(f"Kubernetes {context} response must be an object")
    return payload


def object_field(payload: KubernetesObject, field: str) -> KubernetesObject:
    """Return an optional object field or reject a field with the wrong shape."""

    value = payload.get(field)
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise KubernetesPayloadError(f"Kubernetes field {field!r} must be an object")
    return value


def object_list(value: object, *, context: str) -> list[KubernetesObject]:
    """Return an optional list of objects or reject malformed entries."""

    if value is None:
        return []
    if not isinstance(value, list):
        raise KubernetesPayloadError(f"Kubernetes {context} must be a list")
    entries: list[KubernetesObject] = []
    for entry in value:
        if not isinstance(entry, Mapping):
            raise KubernetesPayloadError(f"Kubernetes {context} must contain objects")
        entries.append(entry)
    return entries


def integer_field(
    payload: KubernetesObject,
    field: str,
    *,
    default: int,
    minimum: int,
) -> int:
    """Read an integer field without coercing strings, bools, or bad values."""

    value = payload.get(field)
    if value is None:
        return default
    if type(value) is not int or value < minimum:
        raise KubernetesPayloadError(
            f"Kubernetes field {field!r} must be an integer >= {minimum}"
        )
    return value
