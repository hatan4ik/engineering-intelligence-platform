from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Protocol

from .store import FeedbackEvent, FeedbackOutcome


class FeedbackSink(Protocol):
    def append(self, event: FeedbackEvent) -> bool: ...


@dataclass(frozen=True)
class CapturedOutcome:
    event: FeedbackEvent
    inserted: bool


class OutcomeFeedbackRecorder:
    def __init__(self, sink: FeedbackSink) -> None:
        self.sink = sink

    def record_pr_closed(
        self,
        *,
        repository: str,
        pr_number: int,
        service: str | None,
        merged: bool,
        reverted: bool = False,
        risk_score: int | None = None,
        risk_signal: str = "not-reviewed",
        utility_signal: str = "not-reviewed",
    ) -> CapturedOutcome:
        outcome = FeedbackOutcome.REVERTED if reverted else (
            FeedbackOutcome.ACCEPTED if merged else FeedbackOutcome.REJECTED
        )
        event = FeedbackEvent(
            event_id=f"github-pr:{repository}:{pr_number}:{outcome.value}",
            capability="pr-guardian",
            subject_id=f"{repository}#{pr_number}",
            outcome=outcome,
            service=service,
            metadata={
                "repository": repository,
                "pr_number": str(pr_number),
                "risk_signal": risk_signal,
                "utility_signal": utility_signal,
                **({"risk_score": str(risk_score)} if risk_score is not None else {}),
            },
        )
        return CapturedOutcome(event, self.sink.append(event))

    def record_deployment(
        self,
        *,
        deployment_id: str,
        service: str,
        environment: str,
        succeeded: bool,
        risk_score: int | None = None,
        metadata: Mapping[str, str] | None = None,
    ) -> CapturedOutcome:
        outcome = FeedbackOutcome.CORRECT if succeeded else FeedbackOutcome.INCORRECT
        event = FeedbackEvent(
            event_id=f"deployment:{deployment_id}:{outcome.value}",
            capability="predictive-risk",
            subject_id=deployment_id,
            outcome=outcome,
            service=service,
            metadata={
                "environment": environment,
                **({"risk_score": str(risk_score)} if risk_score is not None else {}),
                **dict(metadata or {}),
            },
        )
        return CapturedOutcome(event, self.sink.append(event))

    def record_incident_rca(
        self,
        *,
        incident_id: str,
        service: str,
        hypothesis_id: str,
        confirmed: bool,
        actor: str | None = None,
    ) -> CapturedOutcome:
        outcome = FeedbackOutcome.CORRECT if confirmed else FeedbackOutcome.INCORRECT
        event = FeedbackEvent(
            event_id=f"incident-rca:{incident_id}:{hypothesis_id}:{outcome.value}",
            capability="incident-intelligence",
            subject_id=f"{incident_id}:{hypothesis_id}",
            outcome=outcome,
            service=service,
            actor=actor,
            metadata={"incident_id": incident_id, "hypothesis_id": hypothesis_id},
        )
        return CapturedOutcome(event, self.sink.append(event))


def normalize_github_pr_outcome(payload: Mapping[str, object]) -> dict[str, object] | None:
    """Extract terminal PR outcomes along with explicit reviewer labels (shadow pilot)."""
    if str(payload.get("action", "")) != "closed":
        return None
    repository = payload.get("repository")
    pull_request = payload.get("pull_request")
    if not isinstance(repository, Mapping) or not isinstance(pull_request, Mapping):
        raise ValueError("invalid GitHub pull_request outcome payload")
    full_name = str(repository.get("full_name", "")).strip()
    number = int(payload.get("number", 0))
    if not full_name or number <= 0:
        raise ValueError("missing GitHub repository or PR number")
        
    raw_labels = pull_request.get("labels", [])
    labels = [str(l.get("name", "")).lower() for l in raw_labels if isinstance(l, dict)]
    
    risk_labels = [l for l in labels if l in {"eip-pr-guardian/confirmed-risk", "eip-pr-guardian/false-positive"}]
    utility_labels = [l for l in labels if l in {"eip-pr-guardian/useful", "eip-pr-guardian/not-useful"}]
    
    risk_signal = risk_labels[0].replace("eip-pr-guardian/", "") if risk_labels else "not-reviewed"
    utility_signal = utility_labels[0].replace("eip-pr-guardian/", "") if utility_labels else "not-reviewed"

    return {
        "repository": full_name,
        "pr_number": number,
        "merged": bool(pull_request.get("merged", False)),
        "risk_signal": risk_signal,
        "utility_signal": utility_signal,
    }
