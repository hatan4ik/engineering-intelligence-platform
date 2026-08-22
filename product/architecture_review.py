from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Protocol

from intelligence.architecture_guard import ArchitectureRule, ArchitectureViolation, evaluate_architecture


@dataclass(frozen=True)
class ChangedArtifact:
    path: str
    content: str


@dataclass(frozen=True)
class ArchitectureReview:
    violations: tuple[ArchitectureViolation, ...]
    conclusion: str
    summary: str


class ArchitecturePublisher(Protocol):
    def publish(self, review: ArchitectureReview) -> None: ...


def review_architecture(
    artifacts: Iterable[ChangedArtifact],
    *,
    rules: tuple[ArchitectureRule, ...],
    block_severity: int = 4,
) -> ArchitectureReview:
    violations: list[ArchitectureViolation] = []
    for artifact in artifacts:
        violations.extend(evaluate_architecture(artifact.path, artifact.content, rules))
    ordered = tuple(sorted(violations, key=lambda v: (-v.severity, v.path, v.rule_id, v.marker)))
    blocked = any(v.severity >= block_severity for v in ordered)
    conclusion = "failure" if blocked else "neutral" if ordered else "success"
    summary = render_architecture_review(ordered)
    return ArchitectureReview(ordered, conclusion, summary)


def render_architecture_review(violations: tuple[ArchitectureViolation, ...]) -> str:
    marker = "<!-- eip-architecture-guard -->"
    if not violations:
        return f"{marker}\n## Architecture Guard\n\nNo architecture policy violations detected."
    lines = [marker, "## Architecture Guard", "", f"Detected **{len(violations)}** architecture finding(s):", ""]
    for finding in violations:
        lines.append(
            f"- **S{finding.severity} {finding.rule_id}** `{finding.path}`: "
            f"found `{finding.marker}` — {finding.rationale}"
        )
    lines.extend(["", "Findings are deterministic policy results. They do not grant or override deployment authorization."])
    return "\n".join(lines)
