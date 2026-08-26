"""Regression guard: an approval token string must never satisfy the L3 gate.

Board review (security + reliability seats, convergent finding): the executor
previously derived ``approval_verified`` from ``bool(request.approval_token)``,
so any non-empty string bypassed the human-approval requirement on the
non-durable self-healing path. The verified flag must come only from
``verify_approval()`` upstream.
"""
from __future__ import annotations

from remediation.catalog import AutonomyLevel, default_catalog
from remediation.executor import execute_control_loop
from remediation.policy import ActionRequest, ServiceAutonomy


class _Adapter:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def execute(self, runbook_id: str, request: ActionRequest) -> str:
        self.calls.append(("execute", runbook_id))
        return "exec-1"

    def verify(self, signal: str, request: ActionRequest) -> bool:
        return True

    def rollback(self, rollback_id: str, request: ActionRequest) -> str:
        return "rollback-1"


def _policy() -> ServiceAutonomy:
    return ServiceAutonomy(
        service="payments",
        environment="prod",
        level=AutonomyLevel.APPROVE_AND_EXECUTE,  # L3
        certified_runbooks=("aks.rollout.undo",),
        max_blast_radius=5,
    )


def test_raw_token_does_not_satisfy_l3_approval_gate():
    adapter = _Adapter()
    result = execute_control_loop(
        catalog=default_catalog(),
        policy=_policy(),
        request=ActionRequest("payments", "prod", "aks.rollout.undo", 2, approval_token="totally-made-up"),
        adapter=adapter,
        # approval_verified NOT passed -> defaults to False
    )
    assert result.status == "denied"
    assert "approval" in result.policy.reason.lower()
    assert adapter.calls == []  # no mutation reached the adapter


def test_verified_flag_admits_l3_execution():
    adapter = _Adapter()
    result = execute_control_loop(
        catalog=default_catalog(),
        policy=_policy(),
        request=ActionRequest("payments", "prod", "aks.rollout.undo", 2, approval_token="verified:wf"),
        adapter=adapter,
        approval_verified=True,  # produced by verify_approval() upstream
    )
    assert result.status == "succeeded"
    assert adapter.calls == [("execute", "aks.rollout.undo")]
