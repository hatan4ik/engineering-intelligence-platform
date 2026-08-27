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


@dataclass(frozen=True)
class FileContent:
    """Either the text of a changed file, or why it could not be reviewed.

    A skipped file is not a clean file.  Carrying the reason keeps the review
    from reporting "no violations" about content it never looked at.
    """

    text: str | None
    skip_reason: str | None = None

    @classmethod
    def available(cls, text: str) -> "FileContent":
        return cls(text, None)

    @classmethod
    def unavailable(cls, reason: str) -> "FileContent":
        return cls(None, reason)


@dataclass(frozen=True)
class SkippedPath:
    path: str
    reason: str


@dataclass(frozen=True)
class ChangedPathsReview:
    """An architecture review plus an honest account of its own coverage."""

    violations: tuple[ArchitectureViolation, ...]
    in_scope: int
    reviewed: int
    skipped: tuple[SkippedPath, ...]
    summary: str


class ChangedContentProvider(Protocol):
    """Supplies the pull-request revision of one changed file.

    The pull-request evaluation job checks out the *base* commit and never the
    head, so the content of a changed file has to be fetched rather than read
    from the working tree.  A provider that cannot supply content returns
    ``FileContent.unavailable(reason)``; the file is then reported as skipped,
    never as reviewed-and-clean.
    """

    def read_changed_file(self, path: str) -> FileContent: ...


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


def render_architecture_review(
    violations: tuple[ArchitectureViolation, ...],
    *,
    coverage: ChangedPathsReview | None = None,
) -> str:
    """Render findings, and — when coverage is known — what was actually read.

    Without ``coverage`` this keeps its original wording, which is correct for
    callers that reviewed content they already had in hand.
    """
    marker = "<!-- eip-architecture-guard -->"
    if coverage is not None and coverage.reviewed == 0:
        detail = _coverage_sentence(coverage)
        return f"{marker}\n## Architecture Guard\n\n{detail}"
    if not violations:
        clean = "No architecture policy violations detected."
        if coverage is not None:
            clean = f"{clean} {_coverage_sentence(coverage)}"
        return f"{marker}\n## Architecture Guard\n\n{clean}"
    lines = [marker, "## Architecture Guard", "", f"Detected **{len(violations)}** architecture finding(s):", ""]
    for finding in violations:
        lines.append(
            f"- **S{finding.severity} {finding.rule_id}** `{finding.path}`: "
            f"found `{finding.marker}` — {finding.rationale}"
        )
    if coverage is not None:
        lines.extend(["", _coverage_sentence(coverage)])
        if coverage.skipped:
            lines.append("")
            lines.extend(
                f"- Not reviewed: `{item.path}` — {item.reason}" for item in coverage.skipped
            )
    lines.extend(["", "Findings are deterministic policy results. They do not grant or override deployment authorization."])
    return "\n".join(lines)


def _coverage_sentence(coverage: ChangedPathsReview) -> str:
    if coverage.in_scope == 0:
        return "No changed file was in scope for an architecture rule."
    if coverage.reviewed == 0:
        return (
            f"Architecture Guard did not run: content was unavailable for all "
            f"{coverage.in_scope} in-scope file(s), so nothing was reviewed."
        )
    text = f"Reviewed {coverage.reviewed} of {coverage.in_scope} in-scope file(s)."
    if coverage.skipped:
        text += f" {len(coverage.skipped)} file(s) could not be reviewed."
    return text


def review_changed_paths(
    paths: Iterable[str],
    *,
    provider: ChangedContentProvider,
    rules: tuple[ArchitectureRule, ...] = DEFAULT_ARCHITECTURE_RULES,
    block_severity: int = 4,
    max_skipped_reported: int = 32,
) -> ChangedPathsReview:
    """Review the changed files some rule could match, and report the coverage.

    Content is fetched lazily so an unrelated pull request costs no requests.
    Files whose content could not be fetched are counted as skipped with their
    reason — never silently treated as clean.
    """
    artifacts: list[ChangedArtifact] = []
    skipped: list[SkippedPath] = []
    in_scope = 0
    for path in paths:
        if not any(fnmatch(path, rule.pattern) for rule in rules):
            continue
        in_scope += 1
        result = provider.read_changed_file(path)
        if result.text is None:
            if len(skipped) < max_skipped_reported:
                skipped.append(SkippedPath(path, result.skip_reason or "content unavailable"))
            continue
        artifacts.append(ChangedArtifact(path, result.text))
    review = review_architecture(artifacts, rules=rules, block_severity=block_severity)
    coverage = ChangedPathsReview(
        violations=review.violations,
        in_scope=in_scope,
        reviewed=len(artifacts),
        skipped=tuple(skipped),
        summary="",
    )
    return ChangedPathsReview(
        violations=review.violations,
        in_scope=in_scope,
        reviewed=len(artifacts),
        skipped=tuple(skipped),
        summary=architecture_summary_line(coverage),
    )


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


def architecture_summary_line(coverage: ChangedPathsReview) -> str:
    """A short, coverage-honest summary; the full rendering goes in the comment.

    When nothing was reviewed this says the review did not run.  It must never
    report an absence of findings about files it never read.
    """
    sentence = _coverage_sentence(coverage)
    if coverage.reviewed == 0:
        return sentence
    if not coverage.violations:
        return f"No architecture policy violations detected. {sentence}"
    paths = len({item.path for item in coverage.violations})
    return (
        f"{len(coverage.violations)} architecture finding(s) across {paths} file(s). "
        f"{sentence}"
    )


def skipped_records(skipped: tuple[SkippedPath, ...]) -> list[dict[str, object]]:
    """Serialize skipped paths for the workflow-transfer observation record."""
    return [{"path": item.path, "reason": item.reason} for item in skipped]


def coverage_from_records(
    violations: tuple[ArchitectureViolation, ...],
    *,
    reviewed: int,
    in_scope: int,
    skipped: Sequence[Mapping[str, Any]],
    summary: str,
) -> ChangedPathsReview:
    """Rebuild coverage a trusted publisher validated, for rendering only."""
    return ChangedPathsReview(
        violations=violations,
        in_scope=in_scope,
        reviewed=reviewed,
        skipped=tuple(
            SkippedPath(str(item["path"]), str(item["reason"])) for item in skipped
        ),
        summary=summary,
    )
