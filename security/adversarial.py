from __future__ import annotations

from dataclasses import dataclass


SUSPICIOUS_PATTERNS = (
    "ignore previous instructions",
    "reveal system prompt",
    "exfiltrate secret",
    "disable policy",
    "bypass authorization",
    "run this command",
)


@dataclass(frozen=True)
class ContentAssessment:
    suspicious: bool
    matches: tuple[str, ...]


def assess_retrieved_content(text: str) -> ContentAssessment:
    lowered = text.lower()
    matches = tuple(p for p in SUSPICIOUS_PATTERNS if p in lowered)
    return ContentAssessment(bool(matches), matches)


def tool_call_allowed(*, requested_tool: str, allowed_tools: tuple[str, ...], model_requested: bool) -> bool:
    # Model intent never expands the tool allow-list.
    return requested_tool in allowed_tools
