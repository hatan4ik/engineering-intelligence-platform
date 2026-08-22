from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from product.architecture_review import ArchitectureReview
from product.knowledge_maintenance import KnowledgeMaintenancePlan


ARCHITECTURE_MARKER = "<!-- eip-architecture-guard -->"
KNOWLEDGE_MARKER = "<!-- eip-knowledge-decay -->"


class GitHubIntelligenceClient(Protocol):
    def publish_check(
        self,
        *,
        repository: str,
        head_sha: str,
        name: str,
        conclusion: str,
        title: str,
        summary: str,
    ) -> None: ...

    def publish_sticky_comment(
        self,
        *,
        repository: str,
        pr_number: int,
        marker: str,
        body: str,
    ) -> None: ...

    def ensure_maintenance_issue(
        self,
        *,
        repository: str,
        marker: str,
        title: str,
        body: str,
        labels: tuple[str, ...] = (),
    ) -> int: ...


@dataclass
class GitHubArchitecturePublisher:
    client: GitHubIntelligenceClient
    repository: str
    pr_number: int
    head_sha: str

    def publish(self, review: ArchitectureReview) -> None:
        self.client.publish_check(
            repository=self.repository,
            head_sha=self.head_sha,
            name="Engineering Intelligence / Architecture Guard",
            conclusion=review.conclusion,
            title="Architecture Guard",
            summary=review.summary,
        )
        self.client.publish_sticky_comment(
            repository=self.repository,
            pr_number=self.pr_number,
            marker=ARCHITECTURE_MARKER,
            body=review.summary,
        )


@dataclass
class GitHubKnowledgeMaintenancePublisher:
    client: GitHubIntelligenceClient
    repository: str

    def publish(self, plan: KnowledgeMaintenancePlan) -> int | None:
        if not plan.items:
            return None
        highest = max(item.severity for item in plan.items)
        title = f"Engineering knowledge maintenance: {len(plan.items)} finding(s), max severity S{highest}"
        return self.client.ensure_maintenance_issue(
            repository=self.repository,
            marker=KNOWLEDGE_MARKER,
            title=title,
            body=plan.summary,
            labels=("engineering-intelligence", "knowledge-maintenance"),
        )
