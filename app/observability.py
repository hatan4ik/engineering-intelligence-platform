from __future__ import annotations

import os

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor


def configure_tracing() -> None:
    if os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT") is None:
        return
    provider = TracerProvider(resource=Resource.create({"service.name": "engineering-intelligence-platform"}))
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(provider)


def tracer():
    return trace.get_tracer("eip")
