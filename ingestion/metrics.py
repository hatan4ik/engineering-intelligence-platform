from __future__ import annotations

from dataclasses import dataclass, field
from time import perf_counter


@dataclass
class IngestionMetrics:
    counters: dict[str, int] = field(default_factory=dict)
    timings_ms: dict[str, list[float]] = field(default_factory=dict)

    def inc(self, name: str, value: int = 1) -> None:
        self.counters[name] = self.counters.get(name, 0) + value

    def observe_ms(self, name: str, value: float) -> None:
        self.timings_ms.setdefault(name, []).append(value)


class Timer:
    def __init__(self, metrics: IngestionMetrics, name: str) -> None:
        self.metrics = metrics
        self.name = name
        self.started = 0.0

    def __enter__(self):
        self.started = perf_counter()
        return self

    def __exit__(self, exc_type, exc, tb):
        self.metrics.observe_ms(self.name, (perf_counter() - self.started) * 1000.0)
        return False
