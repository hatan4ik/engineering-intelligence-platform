"""Immutable configuration required before application routers are imported.

OpenTelemetry providers must be installed before modules request tracer handles.
This deliberately tiny bootstrap record is the only configuration parsed before
``ApplicationSettings`` is bound by the ASGI lifespan.  It keeps that early
read explicit, injectable, and testable instead of hiding an ambient
``os.environ`` lookup inside observability setup.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping


def _optional(source: Mapping[str, str], name: str) -> str | None:
    value = source.get(name, "").strip()
    return value or None


@dataclass(frozen=True)
class BootstrapSettings:
    """Process-bootstrap inputs that must be known before router import."""

    otlp_endpoint: str | None

    @classmethod
    def from_mapping(cls, source: Mapping[str, str]) -> "BootstrapSettings":
        return cls(otlp_endpoint=_optional(source, "OTEL_EXPORTER_OTLP_ENDPOINT"))

    @classmethod
    def from_environment(cls) -> "BootstrapSettings":
        return cls.from_mapping(os.environ)
