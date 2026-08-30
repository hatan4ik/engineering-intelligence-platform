from __future__ import annotations

from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

_RESOURCE = Resource.create({
    "service.name": "engineering-intelligence-platform",
    "service.namespace": "eip",
})
_configured = False


def _signal_endpoint(endpoint: str, signal: str) -> str:
    """Preserve the OTLP base-endpoint semantics used by the SDK environment key."""

    return endpoint.rstrip("/") + f"/v1/{signal}"


def configure_tracing(otlp_endpoint: str | None) -> None:
    """Configure OTLP tracing and metrics once from an explicit bootstrap value."""

    global _configured
    if _configured or otlp_endpoint is None:
        return

    trace_provider = TracerProvider(resource=_RESOURCE)
    trace_provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=_signal_endpoint(otlp_endpoint, "traces")))
    )
    trace.set_tracer_provider(trace_provider)

    metric_reader = PeriodicExportingMetricReader(
        OTLPMetricExporter(endpoint=_signal_endpoint(otlp_endpoint, "metrics"))
    )
    metrics.set_meter_provider(MeterProvider(resource=_RESOURCE, metric_readers=[metric_reader]))
    _configured = True


def tracer():
    return trace.get_tracer("eip")


def meter():
    return metrics.get_meter("eip")
