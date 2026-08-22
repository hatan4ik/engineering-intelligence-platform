from __future__ import annotations

from dataclasses import dataclass
from fnmatch import fnmatch


@dataclass(frozen=True)
class ArchitectureRule:
    rule_id: str
    pattern: str
    forbidden_markers: tuple[str, ...]
    rationale: str
    severity: int = 3


@dataclass(frozen=True)
class ArchitectureViolation:
    rule_id: str
    path: str
    marker: str
    rationale: str
    severity: int


def evaluate_architecture(path: str, content: str, rules: tuple[ArchitectureRule, ...]) -> tuple[ArchitectureViolation, ...]:
    violations: list[ArchitectureViolation] = []
    for rule in rules:
        if not fnmatch(path, rule.pattern):
            continue
        lowered = content.lower()
        for marker in rule.forbidden_markers:
            if marker.lower() in lowered:
                violations.append(ArchitectureViolation(rule.rule_id, path, marker, rule.rationale, rule.severity))
    return tuple(violations)
