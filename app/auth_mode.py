"""Pure compatibility helpers for header-identity policy.

Header-asserted identity (``X-EIP-Groups`` / ``X-EIP-User``) is a local
development affordance for the deterministic demo backend, which serves only a
fixed in-repo corpus. It must never be trusted when the Azure backend is
serving real, ACL-trimmed data — otherwise a caller chooses their own groups
and reads anything indexed under them. That path is therefore fail-closed:
with an Azure backend a valid Entra JWT or API key is always required,
regardless of any flag.  The live HTTP application uses ``QuerySettings``;
these helpers remain pure for smaller callers and unit tests.
"""
from __future__ import annotations

from typing import Mapping


BACKEND_ENV = "EIP_BACKEND"
AZURE_BACKEND = "azure"
DETERMINISTIC_BACKEND = "deterministic"


def backend_mode(environ: Mapping[str, str]) -> str:
    """Normalize the backend value supplied by an explicit configuration mapping."""

    return str(environ.get(BACKEND_ENV, DETERMINISTIC_BACKEND)).strip().lower() or DETERMINISTIC_BACKEND


def header_identity_permitted(environ: Mapping[str, str]) -> tuple[bool, str | None]:
    """Decide whether request-header identity may be used.

    Returns ``(allowed, refusal_reason)``. When ``allowed`` is False the caller
    must fall through to real authentication (Entra JWT / API key); the reason
    is populated only when header identity was affirmatively refused for the
    Azure backend so the caller can surface a clear error.
    """
    if backend_mode(environ) == AZURE_BACKEND:
        # Real data is served; header identity is never trusted here.
        return False, (
            "header identity is not permitted with the Azure backend; "
            "configure Entra JWT or API-key authentication"
        )
    # Deterministic / demo backend: header identity is permitted by default
    # (no real data is served), but a deployment may require real auth by
    # setting EIP_ALLOW_HEADER_IDENTITY=false.
    flag = environ.get("EIP_ALLOW_HEADER_IDENTITY")
    if flag is None:
        return True, None
    return flag.strip().lower() == "true", None
