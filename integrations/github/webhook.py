from __future__ import annotations

import hashlib
import hmac

REVIEW_ACTIONS = {"opened", "synchronize", "reopened", "ready_for_review"}


def verify_webhook_signature(*, secret: str, body: bytes, signature_header: str | None) -> bool:
    """Verify a GitHub `X-Hub-Signature-256` header against the raw request body.

    Fails closed: a missing secret, missing header, or malformed header is a
    rejection, never a pass-through.
    """
    if not secret or not signature_header:
        return False
    scheme, _, received = signature_header.partition("=")
    if scheme != "sha256" or not received:
        return False
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, received)
