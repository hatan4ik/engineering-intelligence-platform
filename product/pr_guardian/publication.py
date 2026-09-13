"""Recoverable GitHub presentation for an already-recorded PR Guardian review.

The publisher does not make a product decision. It records the safe check and
comment intent in a durable outbox, then leases and delivers each side effect
independently. A delivery that succeeds before a process crash is retried with
the same GitHub identity, rather than becoming an untracked duplicate.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Mapping, assert_never

from company_brain.artifact_outbox import (
    ArtifactDeliveryChannel,
    ArtifactDeliveryIntent,
    ArtifactOutbox,
    LeasedArtifactDelivery,
    ProductArtifact,
    canonical_payload_json,
)
from intelligence.pr_guardian import PRPolicyDecision
from intelligence.risk import RiskAssessment
from integrations.github.pr_guardian import GitHubPRClient, PullRequestEvent
from product.pr_guardian_shadow import observation_comment, observation_from_assessment

from .company_brain import PRGuardianCompanyContext
from .contracts import ProductMode
from .decision_context import render_decision_context
from .enforcement import EnforcementDecision, PublishConclusion


_PRODUCT = "pr-guardian"
_DELIVERY_LEASE = timedelta(minutes=2)
_MAXIMUM_RECOVERY_DELIVERIES = 100


class PRGuardianPublisher:
    """Render, durably record, and recoverably publish a fixed PR decision."""

    def __init__(self, github: GitHubPRClient, outbox: ArtifactOutbox) -> None:
        self._github = github
        self._outbox = outbox

    def publish(
        self,
        *,
        event: PullRequestEvent,
        assessment: RiskAssessment,
        workflow_id: str,
        correlation_id: str,
        changed_services: tuple[str, ...],
        policy: PRPolicyDecision,
        mode: ProductMode,
        conclusion: PublishConclusion,
        enforcement: EnforcementDecision,
        company_context: PRGuardianCompanyContext | None,
        now: datetime | None = None,
    ) -> ProductArtifact:
        """Record then deliver one check/comment artifact for a PR review."""

        if not isinstance(mode, ProductMode):
            raise ValueError("PR Guardian publication mode is invalid")
        if conclusion not in {"neutral", "failure"}:
            raise ValueError("PR Guardian publication conclusion is invalid")
        artifact = self._artifact(
            event=event,
            assessment=assessment,
            workflow_id=workflow_id,
            correlation_id=correlation_id,
            changed_services=changed_services,
            policy=policy,
            mode=mode,
            conclusion=conclusion,
            enforcement=enforcement,
            company_context=company_context,
        )
        self._outbox.record(artifact, recorded_at=now)
        self.deliver_pending(artifact_id=artifact.artifact_id, now=now)
        return artifact

    def deliver_pending(
        self,
        *,
        artifact_id: str | None = None,
        maximum_deliveries: int = _MAXIMUM_RECOVERY_DELIVERIES,
        now: datetime | None = None,
    ) -> int:
        """Deliver due outbox work, retaining failed work for a later retry.

        Callers may name an artifact to complete the current request, or omit
        it in a bounded recovery worker. The method re-raises the first external
        delivery failure only after returning its lease to durable storage.
        """

        if type(maximum_deliveries) is not int or not 1 <= maximum_deliveries <= _MAXIMUM_RECOVERY_DELIVERIES:
            raise ValueError("maximum_deliveries must be between 1 and 100")
        current = _utc(now) if now is not None else datetime.now(timezone.utc)
        delivered = 0
        while delivered < maximum_deliveries:
            delivery = self._outbox.claim_next(
                artifact_id=artifact_id,
                now=current,
                lease_duration=_DELIVERY_LEASE,
            )
            if delivery is None:
                return delivered
            try:
                self._deliver(delivery)
            except Exception as error:
                self._outbox.retry(
                    delivery,
                    error=_delivery_error(delivery, error),
                    retry_at=current + _retry_delay(delivery.attempt),
                )
                raise
            self._outbox.acknowledge(delivery, delivered_at=current)
            delivered += 1
        return delivered

    def _artifact(
        self,
        *,
        event: PullRequestEvent,
        assessment: RiskAssessment,
        workflow_id: str,
        correlation_id: str,
        changed_services: tuple[str, ...],
        policy: PRPolicyDecision,
        mode: ProductMode,
        conclusion: PublishConclusion,
        enforcement: EnforcementDecision,
        company_context: PRGuardianCompanyContext | None,
    ) -> ProductArtifact:
        summary = self._summary(
            event=event,
            assessment=assessment,
            workflow_id=workflow_id,
            changed_services=changed_services,
            policy=policy,
            mode=mode,
            enforcement=enforcement,
            company_context=company_context,
        )
        check_payload = canonical_payload_json(
            {
                "repository": event.repository,
                "head_sha": event.head_sha,
                "name": f"Engineering Intelligence / PR Guardian ({mode.value})",
                "conclusion": conclusion,
                "title": check_title(mode, assessment, enforcement),
                "summary": summary,
            }
        )
        comment_payload = canonical_payload_json(
            {
                "repository": event.repository,
                "pr_number": event.number,
                "body": summary,
            }
        )
        scope_id = f"pr:{event.repository}:{event.number}:{event.head_sha}"
        context_version = company_context.context_version if company_context is not None else "legacy-graph:v1"
        artifact_id = _artifact_id(
            product=_PRODUCT,
            scope_id=scope_id,
            correlation_id=correlation_id,
            context_version=context_version,
            deliveries=(
                ("check", ArtifactDeliveryChannel.GITHUB_CHECK, check_payload),
                ("comment", ArtifactDeliveryChannel.GITHUB_COMMENT, comment_payload),
            ),
        )
        return ProductArtifact(
            artifact_id=artifact_id,
            product=_PRODUCT,
            scope_id=scope_id,
            correlation_id=correlation_id,
            context_version=context_version,
            deliveries=(
                ArtifactDeliveryIntent(
                    delivery_key="check",
                    channel=ArtifactDeliveryChannel.GITHUB_CHECK,
                    idempotency_key=_delivery_idempotency_key(artifact_id, "check"),
                    payload_json=check_payload,
                ),
                ArtifactDeliveryIntent(
                    delivery_key="comment",
                    channel=ArtifactDeliveryChannel.GITHUB_COMMENT,
                    idempotency_key=_delivery_idempotency_key(artifact_id, "comment"),
                    payload_json=comment_payload,
                ),
            ),
        )

    @staticmethod
    def _summary(
        *,
        event: PullRequestEvent,
        assessment: RiskAssessment,
        workflow_id: str,
        changed_services: tuple[str, ...],
        policy: PRPolicyDecision,
        mode: ProductMode,
        enforcement: EnforcementDecision,
        company_context: PRGuardianCompanyContext | None,
    ) -> str:
        observation = observation_from_assessment(
            event=event,
            assessment=assessment,
            workflow_id=workflow_id,
            changed_services=changed_services,
            would_require_extended_tests=policy.require_extended_tests,
            would_require_additional_approval=policy.require_additional_approval,
            would_block=policy.block_merge,
            # The service has recorded the workflow, but the standalone
            # shadow runner is responsible for a full chain verification.
            # Do not claim that verification happened in this request path.
            audit_chain_verified=False,
            mode=mode.value,
            enforcement=enforcement.as_dict(),
        )
        summary = observation_comment(observation)
        if company_context is not None:
            summary += "\n\n" + render_decision_context(company_context)
        return summary

    def _deliver(self, delivery: LeasedArtifactDelivery) -> None:
        payload = _payload(delivery.intent.payload_json)
        match delivery.intent.channel:
            case ArtifactDeliveryChannel.GITHUB_CHECK:
                self._github.publish_check(
                    repository=_text(payload, "repository"),
                    head_sha=_text(payload, "head_sha"),
                    name=_text(payload, "name"),
                    conclusion=_check_conclusion(payload),
                    title=_text(payload, "title"),
                    summary=_text(payload, "summary"),
                    external_id=delivery.intent.idempotency_key,
                )
            case ArtifactDeliveryChannel.GITHUB_COMMENT:
                self._github.publish_comment(
                    repository=_text(payload, "repository"),
                    pr_number=_positive_int(payload, "pr_number"),
                    body=_text(payload, "body"),
                )
            case _ as unreachable:
                assert_never(unreachable)


def check_title(
    mode: ProductMode,
    assessment: RiskAssessment,
    decision: EnforcementDecision,
) -> str:
    """Render the check title from a decision the use case already made."""

    risk = f"{assessment.score}/100 ({assessment.band})"
    match mode:
        case ProductMode.ADVISORY:
            return f"Advisory risk: {risk} — this check does not block merges"
        case ProductMode.ENFORCE:
            if decision.would_block:
                return f"Blocked by {decision.rule}: risk {risk}"
            return f"Enforcing risk: {risk} — no blocking rule fired"
        case ProductMode.SHADOW:
            return f"Shadow risk: {risk}"
        case _ as unreachable:
            assert_never(unreachable)


def _artifact_id(
    *,
    product: str,
    scope_id: str,
    correlation_id: str,
    context_version: str,
    deliveries: tuple[tuple[str, ArtifactDeliveryChannel, str], ...],
) -> str:
    payload = canonical_payload_json(
        {
            "product": product,
            "scope_id": scope_id,
            "correlation_id": correlation_id,
            "context_version": context_version,
            "deliveries": [
                {"delivery_key": key, "channel": channel.value, "payload_json": delivery_payload}
                for key, channel, delivery_payload in deliveries
            ],
        }
    )
    return "artifact:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _delivery_idempotency_key(artifact_id: str, delivery_key: str) -> str:
    return "delivery:" + hashlib.sha256(f"{artifact_id}:{delivery_key}".encode("utf-8")).hexdigest()


def _payload(value: str) -> Mapping[str, object]:
    try:
        payload: object = json.loads(value)
    except json.JSONDecodeError as error:
        raise RuntimeError("stored PR Guardian publication payload is invalid") from error
    if not isinstance(payload, dict) or not all(isinstance(key, str) for key in payload):
        raise RuntimeError("stored PR Guardian publication payload must be an object")
    return payload


def _text(payload: Mapping[str, object], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value:
        raise RuntimeError(f"stored PR Guardian publication field {field} is invalid")
    return value


def _positive_int(payload: Mapping[str, object], field: str) -> int:
    value = payload.get(field)
    if type(value) is not int or value < 1:
        raise RuntimeError(f"stored PR Guardian publication field {field} is invalid")
    return value


def _check_conclusion(payload: Mapping[str, object]) -> str:
    conclusion = _text(payload, "conclusion")
    if conclusion not in {"neutral", "failure"}:
        raise RuntimeError("stored PR Guardian publication conclusion is invalid")
    return conclusion


def _retry_delay(attempt: int) -> timedelta:
    # A retry is capped so a transient GitHub outage remains recoverable without
    # allowing one stale artifact to schedule unboundedly far into the future.
    return timedelta(seconds=min(2 ** max(attempt - 1, 0), 300))


def _delivery_error(delivery: LeasedArtifactDelivery, error: Exception) -> str:
    # The outbox record is broadly operationally visible. Retain a diagnosis
    # class without copying an upstream body, URL, token, or source content.
    return f"{delivery.intent.channel.value} delivery failed: {type(error).__name__}"


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("publication time must include a timezone")
    return value.astimezone(timezone.utc)
