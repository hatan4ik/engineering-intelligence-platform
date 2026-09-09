"""PR Guardian publication records intent before retryable GitHub effects."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from company_brain.artifact_outbox import (
    ArtifactDeliveryStatus,
    ArtifactDeliveryState,
    LeasedArtifactDelivery,
    ProductArtifact,
    SqliteArtifactOutbox,
)
from intelligence.pr_guardian import PRPolicyDecision
from intelligence.risk import RiskAssessment, RiskFactor
from integrations.github.pr_guardian import ChangedFile, PullRequestEvent
from product.pr_guardian.enforcement import EnforcementDecision
from product.pr_guardian.contracts import ProductMode
from product.pr_guardian.publication import PRGuardianPublisher


NOW = datetime(2026, 9, 9, 12, 0, tzinfo=timezone.utc)


class FlakyGitHub:
    def __init__(self) -> None:
        self.checks: list[dict[str, object]] = []
        self.comment_attempts = 0
        self.comments: list[dict[str, object]] = []

    def list_changed_files(self, repository: str, pr_number: int) -> list[ChangedFile]:
        return []

    def publish_check(self, **kwargs: object) -> None:
        self.checks.append(kwargs)

    def publish_comment(self, **kwargs: object) -> None:
        self.comment_attempts += 1
        if self.comment_attempts == 1:
            raise RuntimeError("simulated GitHub comment failure")
        self.comments.append(kwargs)


class CapturingOutbox:
    """Records the generated artifact while delegating real durable behavior."""

    def __init__(self, delegate: SqliteArtifactOutbox) -> None:
        self.delegate = delegate
        self.artifacts: list[ProductArtifact] = []

    def record(self, artifact: ProductArtifact, *, recorded_at: datetime | None = None) -> bool:
        self.artifacts.append(artifact)
        return self.delegate.record(artifact, recorded_at=recorded_at)

    def claim_next(
        self,
        *,
        now: datetime | None = None,
        lease_duration: timedelta = timedelta(minutes=1),
        artifact_id: str | None = None,
    ) -> LeasedArtifactDelivery | None:
        return self.delegate.claim_next(
            now=now,
            lease_duration=lease_duration,
            artifact_id=artifact_id,
        )

    def acknowledge(self, delivery: LeasedArtifactDelivery, *, delivered_at: datetime | None = None) -> None:
        self.delegate.acknowledge(delivery, delivered_at=delivered_at)

    def retry(self, delivery: LeasedArtifactDelivery, *, error: str, retry_at: datetime) -> None:
        self.delegate.retry(delivery, error=error, retry_at=retry_at)

    def statuses(self, artifact_id: str) -> tuple[ArtifactDeliveryStatus, ...]:
        return self.delegate.statuses(artifact_id)


def _publisher(tmp_path: Path) -> tuple[PRGuardianPublisher, FlakyGitHub, CapturingOutbox]:
    github = FlakyGitHub()
    outbox = CapturingOutbox(SqliteArtifactOutbox(tmp_path / "outbox.db"))
    return PRGuardianPublisher(github, outbox), github, outbox


def _assessment() -> RiskAssessment:
    return RiskAssessment(
        score=12,
        band="low",
        blast_radius=(),
        factors=(RiskFactor("documentation-only", 0, "Documentation changed"),),
    )


def test_failed_comment_is_retained_and_retried_without_replaying_the_check(tmp_path: Path) -> None:
    publisher, github, outbox = _publisher(tmp_path)

    with pytest.raises(RuntimeError, match="simulated GitHub comment failure"):
        publisher.publish(
            event=PullRequestEvent("acme/platform", 42, "deadbeef", "opened"),
            assessment=_assessment(),
            workflow_id="pr:acme/platform:42",
            correlation_id="corr-42",
            changed_services=(),
            policy=PRPolicyDecision(False, False, False),
            mode=ProductMode.SHADOW,
            conclusion="neutral",
            enforcement=EnforcementDecision(False, "mode-not-enforcing"),
            company_context=None,
            now=NOW,
        )

    artifact = outbox.artifacts[0]
    statuses = outbox.statuses(artifact.artifact_id)
    assert [item.state for item in statuses] == [
        ArtifactDeliveryState.DELIVERED,
        ArtifactDeliveryState.PENDING,
    ]
    assert statuses[1].last_error == "github_comment delivery failed: RuntimeError"
    external_id = github.checks[0]["external_id"]
    assert isinstance(external_id, str) and external_id.startswith("delivery:")

    assert publisher.deliver_pending(artifact_id=artifact.artifact_id, now=NOW + timedelta(seconds=1)) == 1
    assert len(github.checks) == 1
    assert github.comment_attempts == 2
    assert len(github.comments) == 1
    assert all(item.state is ArtifactDeliveryState.DELIVERED for item in outbox.statuses(artifact.artifact_id))
