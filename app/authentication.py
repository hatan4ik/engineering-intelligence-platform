"""Construct trusted request authenticators from typed process settings."""

from __future__ import annotations

from app.entra_identity import EntraPrincipalStore, EntraSettings
from app.gateway import ApiKeyPrincipalStore, PrincipalAuthenticator
from app.settings import AuthenticationSettings, SettingsError


def configured_authenticator(settings: AuthenticationSettings) -> PrincipalAuthenticator:
    """Return the selected identity adapter without reading process environment."""

    if settings.mode == "api-key":
        return ApiKeyPrincipalStore.from_serialized(settings.api_key_principals_json)
    if (
        settings.entra_tenant_id is None
        or settings.entra_audience is None
        or settings.entra_jwks_url is None
    ):
        raise SettingsError("incomplete Entra settings reached authentication composition")
    return EntraPrincipalStore(
        EntraSettings(
            tenant_id=settings.entra_tenant_id,
            audience=settings.entra_audience,
            allowed_issuers=settings.entra_allowed_issuers,
            jwks_url=settings.entra_jwks_url,
        )
    )
