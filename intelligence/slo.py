from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SLOContext:
    target: float
    current: float
    error_budget_remaining: float

    @property
    def breached(self) -> bool:
        return self.current < self.target

    @property
    def budget_exhausted(self) -> bool:
        return self.error_budget_remaining <= 0


def remediation_urgency(ctx: SLOContext) -> str:
    if ctx.budget_exhausted and ctx.breached:
        return "critical"
    if ctx.breached:
        return "high"
    if ctx.error_budget_remaining < 0.25:
        return "elevated"
    return "normal"
