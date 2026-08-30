"""Header-identity is fail-closed for the Azure backend (board finding S-F1)."""
from __future__ import annotations

from app.auth_mode import backend_mode, header_identity_permitted


def test_deterministic_backend_permits_header_identity_by_default():
    allowed, reason = header_identity_permitted({})
    assert allowed is True and reason is None


def test_deterministic_backend_can_require_real_auth():
    allowed, reason = header_identity_permitted(
        {"EIP_BACKEND": "deterministic", "EIP_ALLOW_HEADER_IDENTITY": "false"}
    )
    assert allowed is False and reason is None


def test_azure_backend_refuses_header_identity_regardless_of_flag():
    allowed, reason = header_identity_permitted(
        {"EIP_BACKEND": "azure", "EIP_ALLOW_HEADER_IDENTITY": "true"}
    )  # cannot re-enable it
    assert allowed is False
    assert reason and "azure backend" in reason.lower()


def test_backend_mode_is_normalized_once_for_all_callers():
    source = {"EIP_BACKEND": " Azure "}

    assert backend_mode(source) == "azure"
    allowed, reason = header_identity_permitted(source)
    assert allowed is False
    assert reason and "azure backend" in reason.lower()
