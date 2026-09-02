"""Application composition root for the Engineering Intelligence Platform."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from opentelemetry.trace import SpanKind
from starlette.responses import Response

from app.bootstrap_settings import BootstrapSettings
from app.observability import configure_tracing, tracer
from app.request_context import bind_request_context, request_trace_context
from telemetry.trace_context import TraceContext

# Router modules take tracer handles at import time, so the one genuinely early
# process setting is parsed into an immutable bootstrap record first. Request
# serving configuration still belongs to ApplicationSettings and the lifespan.
_BOOTSTRAP_SETTINGS = BootstrapSettings.from_environment()
configure_tracing(_BOOTSTRAP_SETTINGS.otlp_endpoint)

from app.operations.routes import router as operations_router  # noqa: E402
from app.portal_api import router as portal_router  # noqa: E402
from app.pr_guardian_api import router as pr_guardian_router  # noqa: E402
from app.query_api import router as query_router  # noqa: E402
from app.runtime_wiring import (  # noqa: E402
    capability_report,
    control_report,
    configure_capabilities,
    release_capabilities,
)
from app.settings import (  # noqa: E402
    ApplicationSettings,
    SettingsError,
    settings_for_application,
)


def _lifespan(
    configured_settings: ApplicationSettings | None,
):
    """Build a lifespan that binds one immutable settings record to the app."""

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        try:
            settings = configured_settings or ApplicationSettings.from_environment()
        except SettingsError as error:
            raise RuntimeError(f"invalid application configuration: {error}") from error
        application.state.eip_settings = settings
        configured: tuple[str, ...] = ()
        try:
            configured = configure_capabilities(application, settings)
            yield
        finally:
            release_capabilities(application, configured)
            if configured_settings is None and hasattr(application.state, "eip_settings"):
                delattr(application.state, "eip_settings")

    return lifespan


def create_app(settings: ApplicationSettings | None = None) -> FastAPI:
    """Compose transport adapters around explicit capabilities and settings.

    Production lets the lifespan parse and validate the process environment at
    startup. Tests and embedding hosts may pass an already-built immutable
    settings record instead, so no route has to depend on ambient state.
    """

    application = FastAPI(
        title="Engineering Intelligence Platform",
        version="0.6.0",
        lifespan=_lifespan(settings),
    )
    if settings is not None:
        application.state.eip_settings = settings

    @application.middleware("http")
    async def bind_observability_context(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        """Bind one correlation ID and W3C parent before any route can run."""

        try:
            correlation_id = bind_request_context(request)
        except ValueError as error:
            return JSONResponse(status_code=400, content={"detail": str(error)})
        trace_context = request_trace_context(request)
        with tracer().start_as_current_span(
            "eip.http.request",
            context=trace_context.otel_context(),
            kind=SpanKind.SERVER,
        ) as span:
            span.set_attribute("eip.correlation_id", str(correlation_id))
            span.set_attribute("http.request.method", request.method)
            response = await call_next(request)
            span.set_attribute("http.response.status_code", response.status_code)
            route = request.scope.get("route")
            path = getattr(route, "path", None)
            if isinstance(path, str):
                span.set_attribute("http.route", path)
            response.headers.setdefault("x-correlation-id", str(correlation_id))
            for name, value in TraceContext.current().headers().items():
                response.headers.setdefault(name, value)
            return response

    application.include_router(query_router)
    application.include_router(pr_guardian_router)
    application.include_router(portal_router)
    application.include_router(operations_router)

    @application.get("/healthz", response_model=None)
    def healthz() -> dict[str, object] | JSONResponse:
        try:
            effective_settings = settings_for_application(application)
        except SettingsError as error:
            return JSONResponse(
                status_code=503,
                content={"status": "unavailable", "detail": str(error)},
            )
        return {
            "status": "ok",
            "capabilities": capability_report(
                application, settings=effective_settings
            ),
            "controls": control_report(effective_settings),
        }

    return application
