import hashlib

import pytest

from app.gateway import (
    ApiKeyPrincipalStore,
    GatewayAuthError,
    GatewayPolicyError,
    authorize_request,
    redact_sensitive,
)


def store():
    key = "correct-horse-battery-staple"
    digest = hashlib.sha256(key.encode()).hexdigest()
    return key, ApiKeyPrincipalStore({
        digest: {
            "subject": "nathan@example",
            "groups": ["engineering", "payments"],
            "max_request_usd": 0.10,
            "allowed_model_tiers": ["standard", "advanced"],
        }
    })


def test_authenticated_claims_are_trusted_source_for_groups():
    key, principals = store()
    result = authorize_request(
        question="how does payments auth work?",
        api_key=key,
        requested_model_tier="standard",
        estimated_cost_usd=0.05,
        store=principals,
    )
    assert result.principal.subject == "nathan@example"
    assert result.principal.groups == ("engineering", "payments")


def test_invalid_key_fails_closed():
    _, principals = store()
    with pytest.raises(GatewayAuthError):
        principals.authenticate("wrong")


def test_sensitive_input_is_redacted_before_model_context():
    sanitized, count = redact_sensitive("debug token=abc123 and Authorization: Bearer eyJ.test.value")
    assert "abc123" not in sanitized
    assert "eyJ.test.value" not in sanitized
    assert count >= 2


def test_request_budget_is_enforced_independent_of_model():
    key, principals = store()
    with pytest.raises(GatewayPolicyError, match="cost budget"):
        authorize_request(
            question="analyze architecture",
            api_key=key,
            requested_model_tier="advanced",
            estimated_cost_usd=0.50,
            store=principals,
        )


def test_complex_request_routes_to_advanced_when_allowed():
    key, principals = store()
    result = authorize_request(
        question="perform root cause analysis of this incident architecture",
        api_key=key,
        requested_model_tier=None,
        estimated_cost_usd=0.05,
        store=principals,
    )
    assert result.model_tier == "advanced"


def test_disallowed_model_tier_is_rejected():
    key, principals = store()
    with pytest.raises(GatewayPolicyError, match="model tier"):
        authorize_request(
            question="test",
            api_key=key,
            requested_model_tier="premium-unbounded",
            estimated_cost_usd=0.01,
            store=principals,
        )
