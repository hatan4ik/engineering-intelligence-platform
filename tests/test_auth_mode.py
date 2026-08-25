"""Header-identity is fail-closed for the Azure backend (board finding S-F1)."""
from __future__ import annotations

from app.auth_mode import header_identity_permitted


def test_deterministic_backend_permits_header_identity_by_default(monkeypatch):
    monkeypatch.delenv("EIP_BACKEND", raising=False)
    monkeypatch.delenv("EIP_ALLOW_HEADER_IDENTITY", raising=False)
    allowed, reason = header_identity_permitted()
    assert allowed is True and reason is None


def test_deterministic_backend_can_require_real_auth(monkeypatch):
    monkeypatch.setenv("EIP_BACKEND", "deterministic")
    monkeypatch.setenv("EIP_ALLOW_HEADER_IDENTITY", "false")
    allowed, reason = header_identity_permitted()
    assert allowed is False and reason is None


def test_azure_backend_refuses_header_identity_regardless_of_flag(monkeypatch):
    monkeypatch.setenv("EIP_BACKEND", "azure")
    monkeypatch.setenv("EIP_ALLOW_HEADER_IDENTITY", "true")  # cannot re-enable it
    allowed, reason = header_identity_permitted()
    assert allowed is False
    assert reason and "azure backend" in reason.lower()
