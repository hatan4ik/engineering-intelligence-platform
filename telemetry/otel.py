from __future__ import annotations

from app.observability import meter
from telemetry.events import OperationEvent


class OpenTelemetrySink:
    """Projects OperationEvent into bounded OpenTelemetry metrics.

    High-cardinality correlation/user/repo values are intentionally excluded from
    metric labels. Correlation remains available in traces/audit events.
    """

    def __init__(self) -> None:
        m = meter()
        self.operations = m.create_counter("eip.control_plane.operations", unit="1")
        self.latency = m.create_histogram("eip.control_plane.latency", unit="ms")
        self.cost = m.create_counter("eip.ai.cost", unit="USD")
        self.tokens = m.create_counter("eip.ai.tokens", unit="1")

    @staticmethod
    def _attrs(event: OperationEvent) -> dict[str, str]:
        return {
            "operation": event.operation,
            "component": event.component,
            "outcome": event.outcome,
            "service": event.service or "unknown",
            "agent": event.agent or "unknown",
            "model": event.model or "none",
        }

    def emit(self, event: OperationEvent) -> None:
        attrs = self._attrs(event)
        self.operations.add(1, attrs)
        self.latency.record(max(0.0, event.latency_ms), attrs)
        if event.total_cost_usd:
            self.cost.add(event.total_cost_usd, attrs)
        if event.input_tokens:
            self.tokens.add(event.input_tokens, {**attrs, "direction": "input"})
        if event.output_tokens:
            self.tokens.add(event.output_tokens, {**attrs, "direction": "output"})
