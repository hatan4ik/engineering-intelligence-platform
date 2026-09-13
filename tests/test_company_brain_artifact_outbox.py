"""External publication work is durable, leased, independently retried, and fenced."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from company_brain import (
    ArtifactDeliveryChannel,
    ArtifactDeliveryIntent,
    ArtifactDeliveryState,
    ArtifactOutboxError,
    ProductArtifact,
    SqliteArtifactOutbox,
    canonical_payload_json,
)


NOW = datetime(2026, 9, 9, 12, 0, tzinfo=timezone.utc)


def _artifact() -> ProductArtifact:
    return ProductArtifact(
        artifact_id="artifact:pr-guardian-42",
        product="pr-guardian",
        scope_id="pr:acme/payments:42:deadbeef",
        correlation_id="corr-pr-42",
        context_version="world-model:v1:artifact-test",
        deliveries=(
            ArtifactDeliveryIntent(
                "check",
                ArtifactDeliveryChannel.GITHUB_CHECK,
                "delivery:pr-guardian-42:check",
                canonical_payload_json({"head_sha": "deadbeef", "summary": "safe summary"}),
            ),
            ArtifactDeliveryIntent(
                "comment",
                ArtifactDeliveryChannel.GITHUB_COMMENT,
                "delivery:pr-guardian-42:comment",
                canonical_payload_json({"pr_number": 42, "body": "safe summary"}),
            ),
        ),
    )


def test_outbox_persists_each_side_effect_and_retries_only_the_failed_one(tmp_path: Path) -> None:
    outbox = SqliteArtifactOutbox(tmp_path / "outbox.db")
    artifact = _artifact()

    assert outbox.record(artifact, recorded_at=NOW) is True
    assert outbox.record(artifact, recorded_at=NOW) is False
    check = outbox.claim_next(now=NOW)
    assert check is not None and check.intent.delivery_key == "check"
    outbox.acknowledge(check, delivered_at=NOW + timedelta(seconds=1))
    comment = outbox.claim_next(now=NOW + timedelta(seconds=2))
    assert comment is not None and comment.intent.delivery_key == "comment"
    outbox.retry(
        comment,
        error="GitHub API unavailable",
        retry_at=NOW + timedelta(minutes=1),
    )

    assert outbox.claim_next(now=NOW + timedelta(seconds=30)) is None
    retried = outbox.claim_next(now=NOW + timedelta(minutes=1))
    assert retried is not None and retried.intent.delivery_key == "comment"
    assert retried.attempt == 2
    outbox.acknowledge(retried, delivered_at=NOW + timedelta(minutes=1, seconds=1))

    assert [item.state for item in outbox.statuses(artifact.artifact_id)] == [
        ArtifactDeliveryState.DELIVERED,
        ArtifactDeliveryState.DELIVERED,
    ]
    assert [item.attempts for item in outbox.statuses(artifact.artifact_id)] == [1, 2]


def test_expired_lease_is_recovered_and_cannot_be_acknowledged_by_an_old_worker(tmp_path: Path) -> None:
    outbox = SqliteArtifactOutbox(tmp_path / "outbox.db")
    artifact = _artifact()
    outbox.record(artifact, recorded_at=NOW)
    first = outbox.claim_next(now=NOW, lease_duration=timedelta(seconds=30))
    assert first is not None
    recovered = outbox.claim_next(now=NOW + timedelta(seconds=31))
    assert recovered is not None
    assert recovered.intent.delivery_key == first.intent.delivery_key
    assert recovered.lease_token != first.lease_token

    with pytest.raises(ArtifactOutboxError, match="lease token"):
        outbox.acknowledge(first, delivered_at=NOW + timedelta(seconds=31))


def test_conflicting_reuse_of_an_artifact_id_is_refused(tmp_path: Path) -> None:
    outbox = SqliteArtifactOutbox(tmp_path / "outbox.db")
    artifact = _artifact()
    outbox.record(artifact, recorded_at=NOW)
    conflicting = replace(artifact, correlation_id="corr-pr-43")

    with pytest.raises(ArtifactOutboxError, match="conflicts"):
        outbox.record(conflicting, recorded_at=NOW)
