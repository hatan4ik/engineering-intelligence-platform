from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from intelligence.pr_guardian import PRPolicyDecision, render_markdown
from intelligence.risk import RiskAssessment

from .github_events import PullRequestEvent

CHECK_NAME = "engineering-intelligence/change-risk"
COMMENT_MARKER = "<!-- eip-pr-guardian -->"


@dataclass(frozen=True)
class CheckRun:
    repository: str
    head_sha: str
    name: str
    conclusion: str
    title: str
    summary: str


def conclusion_for(policy: PRPolicyDecision) -> str:
    if policy.block_merge:
        return "action_required"
    if policy.require_extended_tests or policy.require_additional_approval:
        return "neutral"
    return "success"


def build_check_run(event: PullRequestEvent, assessment: RiskAssessment, policy: PRPolicyDecision) -> CheckRun:
    return CheckRun(
        repository=event.repository,
        head_sha=event.head_sha,
        name=CHECK_NAME,
        conclusion=conclusion_for(policy),
        title=f"Change risk {assessment.score}/100 ({assessment.band})",
        summary=f"{COMMENT_MARKER}\n{render_markdown(assessment)}",
    )


class CheckPublisher(Protocol):
    def publish(self, check: CheckRun) -> None: ...


class InMemoryCheckPublisher:
    def __init__(self) -> None:
        self.published: list[CheckRun] = []

    def publish(self, check: CheckRun) -> None:
        self.published.append(check)
