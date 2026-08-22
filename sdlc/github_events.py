from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from typing import Protocol

HANDLED_ACTIONS = {"opened", "synchronize", "reopened", "ready_for_review"}


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


@dataclass(frozen=True)
class PullRequestEvent:
    repository: str
    pr_number: int
    action: str
    head_sha: str
    base_ref: str
    head_ref: str
    title: str
    author: str
    delivery_id: str | None = None


def parse_pull_request_event(payload: dict, *, delivery_id: str | None = None) -> PullRequestEvent | None:
    """Normalize a GitHub `pull_request` webhook payload.

    Returns None for actions that must not trigger a review (labels, comments,
    close events) so callers can acknowledge without acting.
    """
    action = str(payload.get("action", ""))
    if action not in HANDLED_ACTIONS:
        return None
    pr = payload.get("pull_request") or {}
    repo = (payload.get("repository") or {}).get("full_name")
    if not repo or "number" not in pr:
        raise ValueError("payload is not a pull_request event")
    return PullRequestEvent(
        repository=str(repo),
        pr_number=int(pr["number"]),
        action=action,
        head_sha=str((pr.get("head") or {}).get("sha", "")),
        base_ref=str((pr.get("base") or {}).get("ref", "")),
        head_ref=str((pr.get("head") or {}).get("ref", "")),
        title=str(pr.get("title", "")),
        author=str((pr.get("user") or {}).get("login", "unknown")),
        delivery_id=delivery_id,
    )


@dataclass(frozen=True)
class ChangedFile:
    path: str
    status: str = "modified"
    additions: int = 0
    deletions: int = 0


class DiffProvider(Protocol):
    def changed_files(self, repository: str, pr_number: int) -> list[ChangedFile]: ...


def parse_changed_files(rows: list[dict]) -> list[ChangedFile]:
    return [
        ChangedFile(
            path=str(row["filename"]),
            status=str(row.get("status", "modified")),
            additions=int(row.get("additions", 0)),
            deletions=int(row.get("deletions", 0)),
        )
        for row in rows
    ]

