from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class OperationEvent:
    correlation_id: str
    operation: str
    component: str
    outcome: str
    latency_ms: float
    service: str | None = None
    repo: str | None = None
    agent: str | None = None
    user: str | None = None
    model: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    search_documents: int = 0
    suspicious_documents: int = 0
    model_cost_usd: float = 0.0
    search_cost_usd: float = 0.0
    tool_cost_usd: float = 0.0
    attributes: dict[str, str] = field(default_factory=dict)

    @property
    def total_cost_usd(self) -> float:
        return self.model_cost_usd + self.search_cost_usd + self.tool_cost_usd


class TelemetrySink(Protocol):
    def emit(self, event: OperationEvent) -> None: ...


class NullTelemetrySink:
    def emit(self, event: OperationEvent) -> None:
        return None


class InMemoryTelemetrySink:
    def __init__(self) -> None:
        self.events: list[OperationEvent] = []

    def emit(self, event: OperationEvent) -> None:
        self.events.append(event)
