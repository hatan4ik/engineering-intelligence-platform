from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CostEvent:
    service: str
    repo: str
    agent: str
    user: str | None
    model_cost_usd: float = 0.0
    search_cost_usd: float = 0.0
    embedding_cost_usd: float = 0.0
    tool_cost_usd: float = 0.0

    @property
    def total_usd(self) -> float:
        return self.model_cost_usd + self.search_cost_usd + self.embedding_cost_usd + self.tool_cost_usd


def aggregate_by(events: list[CostEvent], field: str) -> dict[str, float]:
    totals: dict[str, float] = {}
    for event in events:
        key = str(getattr(event, field) or "unknown")
        totals[key] = totals.get(key, 0.0) + event.total_usd
    return {k: round(v, 6) for k, v in sorted(totals.items())}
