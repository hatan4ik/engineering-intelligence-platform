from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable

from telemetry.events import OperationEvent, TelemetrySink


@dataclass(frozen=True)
class ControlPlaneSloSnapshot:
    total: int
    succeeded: int
    failed: int
    rolled_back: int
    denied: int
    p95_latency_ms: float
    success_rate: float
    rollback_rate: float


class ControlPlaneTelemetry:
    """Emits correlated, low-cardinality telemetry for control-plane phases.

    Payload/evidence contents are deliberately excluded. The sink receives only
    identifiers, phase outcomes, timing and bounded operational attributes.
    """

    def __init__(self, sink: TelemetrySink, *, clock: Callable[[], float] = time.perf_counter) -> None:
        self.sink = sink
        self.clock = clock

    def emit(
        self,
        *,
        correlation_id: str,
        phase: str,
        component: str,
        outcome: str,
        started_at: float,
        service: str | None = None,
        attributes: dict[str, str] | None = None,
    ) -> None:
        self.sink.emit(
            OperationEvent(
                correlation_id=correlation_id,
                operation=phase,
                component=component,
                outcome=outcome,
                latency_ms=max(0.0, (self.clock() - started_at) * 1000.0),
                service=service,
                agent="control-plane",
                attributes=dict(attributes or {}),
            )
        )


def project_control_plane_slo(events: list[OperationEvent]) -> ControlPlaneSloSnapshot:
    terminal = [e for e in events if e.operation == "remediation.terminal"]
    latencies = sorted(max(0.0, e.latency_ms) for e in terminal)
    if latencies:
        idx = min(len(latencies) - 1, max(0, int(round(0.95 * len(latencies) + 0.5)) - 1))
        p95 = latencies[idx]
    else:
        p95 = 0.0
    total = len(terminal)
    succeeded = sum(e.outcome == "succeeded" for e in terminal)
    failed = sum(e.outcome in {"failed", "escalate"} for e in terminal)
    rolled_back = sum(e.outcome == "rolled_back" for e in terminal)
    denied = sum(e.outcome == "denied" for e in terminal)
    return ControlPlaneSloSnapshot(
        total=total,
        succeeded=succeeded,
        failed=failed,
        rolled_back=rolled_back,
        denied=denied,
        p95_latency_ms=p95,
        success_rate=(succeeded / total) if total else 1.0,
        rollback_rate=(rolled_back / total) if total else 0.0,
    )
