from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from typing import Mapping, Protocol


@dataclass(frozen=True)
class GatewayPrincipal:
    subject: str
    groups: tuple[str, ...]
    max_request_usd: float = 0.25
    allowed_model_tiers: tuple[str, ...] = ("standard",)


@dataclass(frozen=True)
class GatewayDecision:
    principal: GatewayPrincipal
    sanitized_question: str
    model_tier: str
    max_request_usd: float
    redactions: int


class GatewayAuthError(PermissionError):
    pass


class GatewayPolicyError(PermissionError):
    pass


class PrincipalAuthenticator(Protocol):
    """The narrow identity port required by gateway policy."""

    def authenticate(self, credential: str | None) -> GatewayPrincipal: ...


class ApiKeyPrincipalStore:
    """Reference identity adapter.

    Production deployments should replace this with Entra/JWT validation. Keys
    are never stored directly: the environment mapping uses sha256(key) -> claims.
    """

    def __init__(self, records: Mapping[str, Mapping[str, object]]) -> None:
        self.records = records

    @classmethod
    def from_serialized(cls, raw: str) -> "ApiKeyPrincipalStore":
        """Build the reference adapter from a configuration-bound JSON string."""

        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            raise ValueError("EIP_API_KEY_PRINCIPALS must be a JSON object")
        return cls(parsed)

    def authenticate(self, api_key: str | None) -> GatewayPrincipal:
        if not api_key:
            raise GatewayAuthError("missing API key")
        digest = hashlib.sha256(api_key.encode()).hexdigest()
        claims = self.records.get(digest)
        if not isinstance(claims, Mapping):
            raise GatewayAuthError("invalid API key")
        subject = str(claims.get("subject") or "")
        if not subject:
            raise GatewayAuthError("principal subject is missing")
        return GatewayPrincipal(
            subject=subject,
            groups=_string_claims(claims.get("groups", []), field="groups"),
            max_request_usd=_cost_claim(claims.get("max_request_usd", 0.25)),
            allowed_model_tiers=_string_claims(
                claims.get("allowed_model_tiers", ["standard"]),
                field="allowed_model_tiers",
            ),
        )


def _string_claims(value: object, *, field: str) -> tuple[str, ...]:
    """Narrow dynamic API-key claims before policy code consumes them."""

    if not isinstance(value, list):
        raise GatewayAuthError(f"principal {field} must be a JSON array")
    values = tuple(sorted({str(item).strip() for item in value if str(item).strip()}))
    if field == "allowed_model_tiers" and not values:
        raise GatewayAuthError("principal allowed_model_tiers must not be empty")
    return values


def _cost_claim(value: object) -> float:
    """Narrow the optional API-key cost ceiling and reject unsafe values."""

    if isinstance(value, bool):
        raise GatewayAuthError("principal max_request_usd must be a non-negative number")
    if not isinstance(value, (int, float, str)):
        raise GatewayAuthError("principal max_request_usd must be a non-negative number")
    try:
        cost = float(value)
    except (TypeError, ValueError) as error:
        raise GatewayAuthError("principal max_request_usd must be a non-negative number") from error
    if not math.isfinite(cost) or cost < 0:
        raise GatewayAuthError("principal max_request_usd must be a non-negative number")
    return cost


_SECRET_PATTERNS = (
    re.compile(r"(?i)(password|passwd|secret|token|api[_-]?key)\s*[:=]\s*([^\s,;]+)"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]+"),
    re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
)


def redact_sensitive(text: str) -> tuple[str, int]:
    sanitized = text
    count = 0
    for pattern in _SECRET_PATTERNS:
        def replacement(match: re.Match[str]) -> str:
            nonlocal count
            count += 1
            if match.lastindex and match.lastindex >= 2:
                return f"{match.group(1)}=[REDACTED]"
            return "[REDACTED]"
        sanitized = pattern.sub(replacement, sanitized)
    return sanitized, count


def choose_model_tier(*, question: str, requested_tier: str | None, principal: GatewayPrincipal) -> str:
    allowed = principal.allowed_model_tiers or ("standard",)
    if requested_tier:
        if requested_tier not in allowed:
            raise GatewayPolicyError("requested model tier is not allowed for principal")
        return requested_tier
    complex_request = len(question) > 1500 or any(
        marker in question.lower() for marker in ("architecture", "root cause", "incident", "migration plan")
    )
    preferred = "advanced" if complex_request and "advanced" in allowed else "standard"
    return preferred if preferred in allowed else allowed[0]


def authorize_request(
    *,
    question: str,
    api_key: str | None,
    requested_model_tier: str | None,
    estimated_cost_usd: float,
    store: PrincipalAuthenticator,
) -> GatewayDecision:
    principal = store.authenticate(api_key)
    if estimated_cost_usd < 0 or estimated_cost_usd > principal.max_request_usd:
        raise GatewayPolicyError("request exceeds principal AI cost budget")
    sanitized, redactions = redact_sensitive(question)
    tier = choose_model_tier(
        question=sanitized,
        requested_tier=requested_model_tier,
        principal=principal,
    )
    return GatewayDecision(principal, sanitized, tier, principal.max_request_usd, redactions)
