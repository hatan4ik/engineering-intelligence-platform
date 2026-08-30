"""Thin HTTP routes for the operational-intelligence application boundary."""

from __future__ import annotations

import hmac
import json
from typing import Final

from fastapi import APIRouter, Header, HTTPException, Request

from app.request_context import request_correlation_id
from integrations.azure_devops.deployment_failure import normalize_service_hook
from resilience.dependencies import DependencyUnavailable

from .capability import OperationsCapability
from .contracts import (
    DeploymentInvestigationResponse,
    IgnoredIncidentResponse,
    IncidentInvestigationResponse,
)
from .normalization import normalize_common_alert
from .presentation import deployment_report, incident_report
from app.settings import ApplicationSettings, SettingsError, settings_for_application


SECRET_HEADER: Final[str] = "X-EIP-Operations-Secret"

router = APIRouter(prefix="/v1/events", tags=["operational-intelligence"])


def verify_webhook_secret(
    provided: str | None,
    expected: str | None,
) -> None:
    """Fail closed when the route secret is absent or does not match."""

    if not expected:
        raise HTTPException(
            status_code=503,
            detail=(
                "operational intelligence is not configured on this deployment: "
                "EIP_OPERATIONS_WEBHOOK_SECRET is unset"
            ),
        )
    # Encode explicitly: compare_digest on str raises TypeError for non-ASCII,
    # and a header is attacker-controlled.
    if not provided or not hmac.compare_digest(
        expected.encode("utf-8"),
        provided.encode("utf-8"),
    ):
        raise HTTPException(status_code=401, detail=f"invalid or missing {SECRET_HEADER} header")


def operations_capability(request: Request) -> OperationsCapability:
    capability = getattr(request.app.state, "operations", None)
    if capability is None:
        raise HTTPException(
            status_code=503,
            detail=(
                "operational intelligence is not configured on this deployment: "
                "set EIP_OPERATIONS_EVIDENCE and EIP_STATE_DIR and restart"
            ),
        )
    if not isinstance(capability, OperationsCapability):
        raise HTTPException(status_code=503, detail="operational intelligence capability is invalid")
    return capability


def request_settings(request: Request) -> ApplicationSettings:
    """Translate an invalid direct-route test configuration into an operator-safe error."""

    try:
        return settings_for_application(request.app)
    except SettingsError as error:
        raise HTTPException(
            status_code=503,
            detail=f"invalid application configuration: {error}",
        ) from error


async def json_object(request: Request) -> dict[str, object]:
    """Read one untrusted JSON object, rejecting arrays and scalar JSON values."""

    try:
        raw: object = json.loads(await request.body())
    except (ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail="request body is not valid JSON") from exc
    if not isinstance(raw, dict):
        raise HTTPException(status_code=400, detail="request body must be a JSON object")
    return {str(key): value for key, value in raw.items()}


@router.post("/deployment", response_model=DeploymentInvestigationResponse)
async def deployment_event(
    request: Request,
    x_eip_operations_secret: str | None = Header(default=None),
) -> DeploymentInvestigationResponse:
    verify_webhook_secret(
        x_eip_operations_secret,
        request_settings(request).operations.webhook_secret,
    )
    capability = operations_capability(request)
    payload = await json_object(request)
    try:
        event = normalize_service_hook(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    correlation_id = request_correlation_id(request)
    try:
        result = await capability.deployment.investigate(event, correlation_id=correlation_id)
    except DependencyUnavailable as exc:
        raise HTTPException(
            status_code=503,
            detail="operational evidence dependency is unavailable; retry the event",
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return deployment_report(event, result)


@router.post("/incident", response_model=IncidentInvestigationResponse | IgnoredIncidentResponse)
async def incident_event(
    request: Request,
    x_eip_operations_secret: str | None = Header(default=None),
) -> IncidentInvestigationResponse | IgnoredIncidentResponse:
    verify_webhook_secret(
        x_eip_operations_secret,
        request_settings(request).operations.webhook_secret,
    )
    capability = operations_capability(request)
    payload = await json_object(request)
    try:
        trigger = normalize_common_alert(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not trigger.fired:
        return IgnoredIncidentResponse()
    correlation_id = request_correlation_id(request)
    try:
        result = await capability.incident.investigate(
            incident_id=trigger.incident_id,
            service=trigger.service,
            environment=trigger.environment,
            correlation_id=correlation_id,
        )
    except DependencyUnavailable as exc:
        raise HTTPException(
            status_code=503,
            detail="operational evidence dependency is unavailable; retry the event",
        ) from exc
    return incident_report(trigger, result)
