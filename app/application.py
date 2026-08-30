"""Application composition root for the Engineering Intelligence Platform."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI

from app.observability import configure_tracing
from app.settings import observability_endpoint_from_environment

# Configure before importing routers so their tracer handles bind to the
# process provider when OTLP is enabled.
configure_tracing(observability_endpoint_from_environment())

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
    application.include_router(query_router)
    application.include_router(pr_guardian_router)
    application.include_router(portal_router)
    application.include_router(operations_router)

    @application.get("/healthz")
    def healthz() -> dict[str, object]:
        effective_settings = settings_for_application(application)
        return {
            "status": "ok",
            "capabilities": capability_report(
                application, settings=effective_settings
            ),
            "controls": control_report(effective_settings),
        }

    return application
