from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from fastapi import APIRouter, Header, HTTPException, Request

from app.authentication import configured_authenticator
from app.gateway import GatewayAuthError, GatewayPrincipal
from app.settings import ApplicationSettings, SettingsError, settings_for_application
from portal.intelligence_view import ServiceIntelligenceView, to_dict as service_to_dict
from portal.portfolio_view import PortfolioIntelligenceView, to_dict as portfolio_to_dict
from portal.timeseries import MetricTrend, serialize_trend


@dataclass(frozen=True)
class PortalPrincipal:
    subject: str
    groups: tuple[str, ...]


class ServiceIntelligenceProvider(Protocol):
    def get_service_view(self, *, service: str, principal: PortalPrincipal) -> ServiceIntelligenceView | None: ...


class PortfolioIntelligenceProvider(Protocol):
    def get_portfolio_view(self, *, principal: PortalPrincipal) -> PortfolioIntelligenceView: ...


class PortfolioTrendProvider(Protocol):
    def get_metric_trend(self, *, metric: str, principal: PortalPrincipal) -> MetricTrend | None: ...


router = APIRouter(prefix="/v1/portal", tags=["engineering-intelligence"])


def _principal(
    *,
    settings: ApplicationSettings,
    authorization: str | None,
    api_key: str | None,
    fallback_user: str | None,
    fallback_groups: str | None,
) -> PortalPrincipal:
    if settings.query.header_identity_permitted:
        groups = tuple(sorted(g.strip() for g in (fallback_groups or "engineering").split(",") if g.strip()))
        return PortalPrincipal(fallback_user or "local-demo", groups)

    try:
        authenticator = configured_authenticator(settings.query.authentication)
        credential = authorization if settings.query.authentication.mode == "entra" else api_key
        auth: GatewayPrincipal = authenticator.authenticate(credential)
    except GatewayAuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except (SettingsError, ValueError) as exc:
        raise HTTPException(status_code=503, detail=f"invalid application configuration: {exc}") from exc
    return PortalPrincipal(auth.subject, auth.groups)


def _request_settings(request: Request) -> ApplicationSettings:
    try:
        return settings_for_application(request.app)
    except SettingsError as exc:
        raise HTTPException(status_code=503, detail=f"invalid application configuration: {exc}") from exc


def _viewer(principal: PortalPrincipal) -> dict[str, object]:
    return {"subject": principal.subject, "group_count": len(principal.groups)}


@router.get("/services/{service}")
def service_intelligence(
    service: str,
    request: Request,
    authorization: str | None = Header(default=None),
    x_eip_api_key: str | None = Header(default=None),
    x_eip_user: str | None = Header(default=None),
    x_eip_groups: str | None = Header(default=None),
) -> dict[str, object]:
    principal = _principal(
        settings=_request_settings(request),
        authorization=authorization,
        api_key=x_eip_api_key,
        fallback_user=x_eip_user,
        fallback_groups=x_eip_groups,
    )
    provider = getattr(request.app.state, "service_intelligence_provider", None)
    if provider is None:
        raise HTTPException(status_code=503, detail="service intelligence provider is not configured")
    view = provider.get_service_view(service=service, principal=principal)
    if view is None:
        raise HTTPException(status_code=404, detail="service not found or not authorized")
    payload = service_to_dict(view)
    payload["viewer"] = _viewer(principal)
    return payload


@router.get("/portfolio")
def portfolio_intelligence(
    request: Request,
    authorization: str | None = Header(default=None),
    x_eip_api_key: str | None = Header(default=None),
    x_eip_user: str | None = Header(default=None),
    x_eip_groups: str | None = Header(default=None),
) -> dict[str, object]:
    principal = _principal(
        settings=_request_settings(request),
        authorization=authorization,
        api_key=x_eip_api_key,
        fallback_user=x_eip_user,
        fallback_groups=x_eip_groups,
    )
    provider = getattr(request.app.state, "portfolio_intelligence_provider", None)
    if provider is None:
        raise HTTPException(status_code=503, detail="portfolio intelligence provider is not configured")
    payload = portfolio_to_dict(provider.get_portfolio_view(principal=principal))
    payload["viewer"] = _viewer(principal)
    return payload


@router.get("/portfolio/trends/{metric}")
def portfolio_trend(
    metric: str,
    request: Request,
    authorization: str | None = Header(default=None),
    x_eip_api_key: str | None = Header(default=None),
    x_eip_user: str | None = Header(default=None),
    x_eip_groups: str | None = Header(default=None),
) -> dict[str, object]:
    principal = _principal(
        settings=_request_settings(request),
        authorization=authorization,
        api_key=x_eip_api_key,
        fallback_user=x_eip_user,
        fallback_groups=x_eip_groups,
    )
    provider = getattr(request.app.state, "portfolio_trend_provider", None)
    if provider is None:
        raise HTTPException(status_code=503, detail="portfolio trend provider is not configured")
    trend = provider.get_metric_trend(metric=metric, principal=principal)
    if trend is None:
        raise HTTPException(status_code=404, detail="metric not found or not authorized")
    payload = serialize_trend(trend)
    payload["viewer"] = _viewer(principal)
    return payload
