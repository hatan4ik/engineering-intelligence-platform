"""Untrusted API-key claims are narrowed before gateway policy consumes them."""

from __future__ import annotations

import hashlib

import pytest

from app.gateway import ApiKeyPrincipalStore, GatewayAuthError


def _store(claims: dict[str, object]) -> tuple[ApiKeyPrincipalStore, str]:
    key = "key"
    return ApiKeyPrincipalStore({hashlib.sha256(key.encode()).hexdigest(): claims}), key


@pytest.mark.parametrize(
    "claims, message",
    [
        ({"subject": "user", "groups": "engineering"}, "groups must be a JSON array"),
        (
            {"subject": "user", "allowed_model_tiers": []},
            "allowed_model_tiers must not be empty",
        ),
        ({"subject": "user", "max_request_usd": False}, "max_request_usd"),
        ({"subject": "user", "max_request_usd": -1}, "max_request_usd"),
    ],
)
def test_api_key_claims_reject_unexpected_dynamic_shapes(claims, message):
    store, key = _store(claims)

    with pytest.raises(GatewayAuthError, match=message):
        store.authenticate(key)
