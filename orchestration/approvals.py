from __future__ import annotations

import hashlib
import hmac
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class Approval:
    workflow_id: str
    approver: str
    plan_hash: str
    issued_at: int
    signature: str


def issue_approval(*, workflow_id: str, approver: str, plan_hash: str, secret: str, now: int | None = None) -> Approval:
    issued_at = int(now or time.time())
    payload = f"{workflow_id}|{approver}|{plan_hash}|{issued_at}".encode()
    signature = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return Approval(workflow_id, approver, plan_hash, issued_at, signature)


def verify_approval(
    approval: Approval,
    *,
    expected_workflow_id: str,
    expected_plan_hash: str,
    secret: str,
    max_age_seconds: int = 900,
    now: int | None = None,
) -> bool:
    current = int(now or time.time())
    if approval.workflow_id != expected_workflow_id or approval.plan_hash != expected_plan_hash:
        return False
    if current - approval.issued_at > max_age_seconds or approval.issued_at > current + 30:
        return False
    payload = f"{approval.workflow_id}|{approval.approver}|{approval.plan_hash}|{approval.issued_at}".encode()
    expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, approval.signature)
