from __future__ import annotations

from dataclasses import dataclass
from fnmatch import fnmatch
from typing import Any, Iterable, Mapping, Protocol, Sequence

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


class ChangedContentProvider(Protocol):
    """Supplies the pull-request revision of one changed file, or None.

    The pull-request evaluation job checks out the *base* commit and never the
    head, so the content of a changed file has to be fetched rather than read
    from the working tree.  Returning None means "content unavailable" and the
    file is simply not reviewed; it never becomes a finding.
    """

    def read_changed_file(self, path: str) -> str | None: ...


# Deterministic, repository-agnostic architecture rules applied on the pull
# request path.  They are advisory in this stage: Architecture Guard findings
# are recorded and rendered, and never influence the PR Guardian check
# conclusion or any enforcement decision.
DEFAULT_ARCHITECTURE_RULES: tuple[ArchitectureRule, ...] = (
    ArchitectureRule(
        rule_id="EIP-ARCH-001",
        pattern="*.tf",
        forbidden_markers=("public_network_access_enabled = true",),
        rationale="Managed data planes must stay on private endpoints.",
        severity=4,
    ),
    ArchitectureRule(
        rule_id="EIP-ARCH-002",
        pattern=".github/workflows/*",
        forbidden_markers=("pull_request_target",),
        rationale=(
            "pull_request_target runs with write scope in the context of untrusted "
            "pull-request code; use a separate trusted publisher workflow instead."
        ),
        severity=4,
    ),
    ArchitectureRule(
        rule_id="EIP-ARCH-003",
        pattern="*.py",
        forbidden_markers=("blocking_authorized = true", '"blocking_authorized": true'),
        rationale=(
            "Merge-blocking authorization is a recorded product decision, never a "
            "code default."
        ),
        severity=5,
    ),
)


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


def review_changed_paths(
    paths: Iterable[str],
    *,
    provider: ChangedContentProvider,
    rules: tuple[ArchitectureRule, ...] = DEFAULT_ARCHITECTURE_RULES,
    block_severity: int = 4,
) -> ArchitectureReview:
    """Review only the changed files some rule could possibly match.

    Content is fetched lazily so an unrelated pull request costs no requests.
    """
    artifacts: list[ChangedArtifact] = []
    for path in paths:
        if not any(fnmatch(path, rule.pattern) for rule in rules):
            continue
        content = provider.read_changed_file(path)
        if content is None:
            continue
        artifacts.append(ChangedArtifact(path, content))
    return review_architecture(artifacts, rules=rules, block_severity=block_severity)


def violation_records(violations: tuple[ArchitectureViolation, ...]) -> list[dict[str, object]]:
    """Serialize findings for the workflow-transfer observation record."""
    return [
        {
            "rule_id": item.rule_id,
            "path": item.path,
            "marker": item.marker,
            "rationale": item.rationale,
            "severity": item.severity,
        }
        for item in violations
    ]


def violations_from_records(records: Sequence[Mapping[str, Any]]) -> tuple[ArchitectureViolation, ...]:
    """Rebuild findings a trusted publisher validated, for rendering only."""
    return tuple(
        ArchitectureViolation(
            rule_id=str(record["rule_id"]),
            path=str(record["path"]),
            marker=str(record["marker"]),
            rationale=str(record["rationale"]),
            severity=int(record["severity"]),
        )
        for record in records
    )


def architecture_summary_line(violations: tuple[ArchitectureViolation, ...]) -> str:
    """A short summary; the full rendering lives in the sticky comment."""
    if not violations:
        return "No architecture policy violations detected."
    paths = len({item.path for item in violations})
    return f"{len(violations)} architecture finding(s) across {paths} file(s)."
