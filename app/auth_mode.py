"""Single source of truth for whether request-header identity is trusted.

Header-asserted identity (``X-EIP-Groups`` / ``X-EIP-User``) is a local
development affordance for the deterministic demo backend, which serves only a
fixed in-repo corpus. It must never be trusted when the Azure backend is
serving real, ACL-trimmed data — otherwise a caller chooses their own groups
and reads anything indexed under them. That path is therefore fail-closed:
with ``EIP_BACKEND=azure`` a valid Entra JWT or API key is always required,
regardless of any flag.
"""
from __future__ import annotations

import os


def header_identity_permitted() -> tuple[bool, str | None]:
    """Decide whether request-header identity may be used.

    Returns ``(allowed, refusal_reason)``. When ``allowed`` is False the caller
    must fall through to real authentication (Entra JWT / API key); the reason
    is populated only when header identity was affirmatively refused for the
    Azure backend so the caller can surface a clear error.
    """
    backend = os.getenv("EIP_BACKEND", "deterministic").strip().lower()
    if backend == "azure":
        # Real data is served; header identity is never trusted here.
        return False, (
            "header identity is not permitted with the Azure backend; "
            "configure Entra JWT or API-key authentication"
        )
    # Deterministic / demo backend: header identity is permitted by default
    # (no real data is served), but a deployment may require real auth by
    # setting EIP_ALLOW_HEADER_IDENTITY=false.
    flag = os.getenv("EIP_ALLOW_HEADER_IDENTITY")
    if flag is None:
        return True, None
    return flag.strip().lower() == "true", None
