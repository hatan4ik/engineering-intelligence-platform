"""The HTTP process consumes one immutable, validated settings record."""

from __future__ import annotations

import hashlib
import json

import pytest
from fastapi.testclient import TestClient

from app.application import create_app
from app.settings import ApplicationSettings, SettingsError


def _azure_mapping() -> dict[str, str]:
    return {
        "EIP_BACKEND": "Azure",
        "AZURE_SEARCH_ENDPOINT": "https://search.example.invalid",
        "AZURE_SEARCH_INDEX": "company-brain",
        "AZURE_OPENAI_ENDPOINT": "https://openai.example.invalid",
        "AZURE_OPENAI_CHAT_DEPLOYMENT": "standard",
    }


def test_default_settings_are_deterministic_and_permit_only_demo_header_identity():
    settings = ApplicationSettings.from_mapping({})

    assert settings.query.backend == "deterministic"
    assert settings.query.header_identity_permitted is True
    assert settings.query.azure_rag is None


def test_azure_backend_is_normalized_and_requires_a_complete_trusted_identity_path():
    with pytest.raises(SettingsError, match="EIP_ENTRA_TENANT_ID"):
        ApplicationSettings.from_mapping(_azure_mapping())


def test_invalid_boolean_and_numeric_inputs_fail_at_startup_parsing():
    with pytest.raises(SettingsError, match="EIP_ALLOW_HEADER_IDENTITY must be true or false"):
        ApplicationSettings.from_mapping({"EIP_ALLOW_HEADER_IDENTITY": "sometimes"})
    with pytest.raises(SettingsError, match="EIP_AUTONOMY_KILL_SWITCH must be true or false"):
        ApplicationSettings.from_mapping({"EIP_AUTONOMY_KILL_SWITCH": "sometimes"})
    with pytest.raises(SettingsError, match="EIP_REQUIRE_OPA must be true or false"):
        ApplicationSettings.from_mapping(
            {"EIP_CONTROL_PLANE_MODE": "temporal", "EIP_REQUIRE_OPA": "sometimes"}
        )
    with pytest.raises(SettingsError, match="EIP_ESTIMATED_REQUEST_USD"):
        ApplicationSettings.from_mapping({"EIP_ESTIMATED_REQUEST_USD": "nan"})


def test_explicit_settings_drive_request_auth_even_if_process_environment_differs(monkeypatch):
    api_key = "test-key"
    settings = ApplicationSettings.from_mapping(
        {
            "EIP_BACKEND": "deterministic",
            "EIP_ALLOW_HEADER_IDENTITY": "false",
            "EIP_AUTH_MODE": "api-key",
            "EIP_API_KEY_PRINCIPALS": json.dumps(
                {
                    hashlib.sha256(api_key.encode()).hexdigest(): {
                        "subject": "test-user",
                        "groups": ["engineering"],
                        "max_request_usd": 1.0,
                        "allowed_model_tiers": ["standard"],
                    }
                }
            ),
        }
    )
    monkeypatch.setenv("EIP_ALLOW_HEADER_IDENTITY", "true")
    app = create_app(settings)

    with TestClient(app) as client:
        response = client.post(
            "/v1/query",
            headers={"X-EIP-API-Key": api_key},
            json={"question": "How should production remediation work?"},
        )

    assert response.status_code == 200
    assert response.json()["model"] == "deterministic-demo"
    assert response.json()["evidence"]


def test_settings_redact_secrets_from_default_dataclass_representation():
    settings = ApplicationSettings.from_mapping(
        {
            "EIP_GITHUB_WEBHOOK_SECRET": "do-not-log-me",
            "EIP_API_KEY_PRINCIPALS": "{}",
        }
    )

    assert "do-not-log-me" not in repr(settings)


def test_failed_startup_does_not_retain_a_stale_settings_snapshot(monkeypatch, tmp_path):
    app = create_app()
    monkeypatch.setenv("EIP_BACKEND", "deterministic")
    monkeypatch.setenv("EIP_OPERATIONS_WEBHOOK_SECRET", "operations-secret")
    monkeypatch.setenv("EIP_OPERATIONS_EVIDENCE", f"fixture:{tmp_path / 'missing.json'}")
    monkeypatch.setenv("EIP_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.delenv("EIP_PR_GUARDIAN_WEBHOOK", raising=False)
    monkeypatch.delenv("EIP_FEEDBACK_DB", raising=False)

    with pytest.raises(RuntimeError, match="missing.json"):
        with TestClient(app):
            pass

    assert not hasattr(app.state, "eip_settings")
    assert not hasattr(app.state, "operations")
