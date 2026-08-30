"""GitHub webhook route for the PR Guardian product wedge."""

from __future__ import annotations

import json

from fastapi import APIRouter, Header, HTTPException, Request

from app.observability import tracer
from app.request_context import request_correlation_id
from feedback.outcome_capture import normalize_github_pr_outcome
from integrations.github.pr_guardian import GitHubAPIError, normalize_pull_request_event
from integrations.github.webhook import REVIEW_ACTIONS, verify_webhook_signature
from app.settings import SettingsError, settings_for_application


router = APIRouter(prefix="/v1/events", tags=["pr-guardian"])
trace = tracer()


@router.post("/github")
async def github_webhook(
    request: Request,
    x_hub_signature_256: str | None = Header(default=None),
    x_github_event: str | None = Header(default=None),
    x_github_delivery: str | None = Header(default=None),
) -> dict[str, object]:
    body = await request.body()
    try:
        secret = settings_for_application(request.app).github_webhook_secret or ""
    except SettingsError as exc:
        raise HTTPException(status_code=503, detail=f"invalid application configuration: {exc}") from exc
    if not verify_webhook_signature(
        secret=secret,
        body=body,
        signature_header=x_hub_signature_256,
    ):
        raise HTTPException(status_code=401, detail="invalid or missing webhook signature")
    if x_github_event == "ping":
        return {"status": "pong"}
    if x_github_event != "pull_request":
        return {"status": "ignored", "event": x_github_event or "unknown"}
    try:
        payload: object = json.loads(body)
        if not isinstance(payload, dict):
            raise ValueError("GitHub pull_request payload must be an object")
        event = normalize_pull_request_event(payload)
        terminal = normalize_github_pr_outcome(payload)
    except (ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if terminal is not None:
        recorder = getattr(request.app.state, "feedback_recorder", None)
        if recorder is not None:
            recorder.record_pr_closed(
                repository=terminal.repository,
                pr_number=terminal.pr_number,
                service=None,
                merged=terminal.merged,
                risk_signal=terminal.risk_signal,
                utility_signal=terminal.utility_signal,
            )
        return {"status": "outcome-recorded", "merged": terminal.merged}

    if event.action not in REVIEW_ACTIONS:
        return {"status": "ignored", "reason": "action does not trigger review"}
    guardian = getattr(request.app.state, "pr_guardian", None)
    if guardian is None:
        raise HTTPException(status_code=503, detail="PR Guardian is not configured on this deployment")
    correlation_id = request_correlation_id(request)
    with trace.start_as_current_span("eip.pr_guardian") as span:
        span.set_attribute("eip.repo", event.repository)
        span.set_attribute("eip.pr", event.number)
        span.set_attribute("eip.delivery_id", x_github_delivery or "")
        try:
            result = await guardian.evaluate(event, correlation_id=correlation_id)
        except GitHubAPIError as error:
            # GitHub delivery retries are safer than pretending the review was
            # published when its dependency was unavailable.
            raise HTTPException(
                status_code=503,
                detail="PR Guardian cannot reach GitHub; retry the delivery",
            ) from error
        span.set_attribute("eip.correlation_id", result.correlation_id)
        span.set_attribute("eip.risk_score", result.assessment.score)
    return {
        "status": "reviewed",
        "workflow_id": result.workflow_id,
        "correlation_id": result.correlation_id,
        "score": result.assessment.score,
        "band": result.assessment.band,
        "conclusion": result.conclusion,
        "changed_services": list(result.changed_services),
    }
