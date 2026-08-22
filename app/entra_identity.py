from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Callable, Mapping

import jwt

from app.gateway import GatewayAuthError, GatewayPrincipal


@dataclass(frozen=True)
class EntraSettings:
    tenant_id: str
    audience: str
    allowed_issuers: tuple[str, ...]
    jwks_url: str

    @classmethod
    def from_environment(cls) -> "EntraSettings":
        tenant = os.environ["EIP_ENTRA_TENANT_ID"]
        audience = os.environ["EIP_ENTRA_AUDIENCE"]
        default_issuer = f"https://login.microsoftonline.com/{tenant}/v2.0"
        issuers = tuple(
            i.strip() for i in os.getenv("EIP_ENTRA_ALLOWED_ISSUERS", default_issuer).split(",") if i.strip()
        )
        return cls(
            tenant_id=tenant,
            audience=audience,
            allowed_issuers=issuers,
            jwks_url=os.getenv(
                "EIP_ENTRA_JWKS_URL",
                f"https://login.microsoftonline.com/{tenant}/discovery/v2.0/keys",
            ),
        )


class EntraPrincipalStore:
    """Validates Entra access tokens and projects trusted claims to gateway policy.

    Signature, audience, issuer and lifetime validation are mandatory. Caller
    supplied group headers are never consulted. Group overage claims fail closed
    until a Graph-backed resolver is explicitly configured.
    """

    def __init__(
        self,
        settings: EntraSettings,
        *,
        key_client: object | None = None,
        decode: Callable[..., Mapping[str, object]] = jwt.decode,
    ) -> None:
        self.settings = settings
        self.key_client = key_client or jwt.PyJWKClient(settings.jwks_url)
        self.decode = decode

    def authenticate(self, bearer_token: str | None) -> GatewayPrincipal:
        if not bearer_token:
            raise GatewayAuthError("missing bearer token")
        token = bearer_token.removeprefix("Bearer ").strip()
        if not token or token == bearer_token and " " in bearer_token:
            raise GatewayAuthError("invalid bearer token")
        try:
            signing_key = self.key_client.get_signing_key_from_jwt(token)
            claims = self.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                audience=self.settings.audience,
                options={"require": ["exp", "iat", "sub"]},
            )
        except Exception as exc:
            raise GatewayAuthError("invalid Entra token") from exc

        issuer = str(claims.get("iss") or "")
        if issuer not in self.settings.allowed_issuers:
            raise GatewayAuthError("untrusted Entra issuer")
        if claims.get("_claim_names") or claims.get("hasgroups"):
            raise GatewayAuthError("group overage requires configured trusted resolver")

        subject = str(claims.get("oid") or claims.get("sub") or "")
        if not subject:
            raise GatewayAuthError("principal subject is missing")
        groups = tuple(sorted({str(g) for g in claims.get("groups", []) if str(g).strip()}))
        roles = tuple(sorted({str(r) for r in claims.get("roles", []) if str(r).strip()}))
        tiers = ("standard", "advanced") if "EIP.AI.Advanced" in roles else ("standard",)
        budget = 1.0 if "EIP.AI.HighBudget" in roles else 0.25
        return GatewayPrincipal(
            subject=subject,
            groups=groups,
            max_request_usd=budget,
            allowed_model_tiers=tiers,
        )
