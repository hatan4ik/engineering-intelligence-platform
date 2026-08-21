from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class UsageRates:
    input_per_million_tokens_usd: float = 0.0
    output_per_million_tokens_usd: float = 0.0
    search_per_1000_queries_usd: float = 0.0
    tool_call_usd: float = 0.0

    def model_cost(self, *, input_tokens: int, output_tokens: int) -> float:
        return round(
            input_tokens / 1_000_000 * self.input_per_million_tokens_usd
            + output_tokens / 1_000_000 * self.output_per_million_tokens_usd,
            8,
        )

    def search_cost(self, *, queries: int = 1) -> float:
        return round(queries / 1000 * self.search_per_1000_queries_usd, 8)

    def tool_cost(self, *, calls: int = 1) -> float:
        return round(calls * self.tool_call_usd, 8)
