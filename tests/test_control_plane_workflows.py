import asyncio

from intelligence.risk import RiskAssessment, RiskFactor
from orchestration.approvals import issue_approval
from state.audit import SqliteAuditLog
from state.store import SqliteStateStore
from control_plane.workflows import ControlPlaneWorkflows


def test_pr_workflow_persists_policy_and_rejects_stale_approval(tmp_path):
    store = SqliteStateStore(tmp_path / "state.db")
    audit = SqliteAuditLog(tmp_path / "audit.db")
    workflows = ControlPlaneWorkflows(store, audit)

    assessment = RiskAssessment(
        score=82,
        band="critical",
        blast_radius=("payments", "ledger"),
        factors=(RiskFactor("security-boundary-change", 20, "identity controls changed"),),
    )
    workflow, policy = asyncio.run(
        workflows.start_pr_review(
            service_id="payments",
            repository="acme/payments",
            pr_number=42,
            assessment=assessment,
        )
    )

    assert policy.require_additional_approval
    assert workflow.plan_hash
    assert store.get_workflow(workflow.workflow_id).plan_hash == workflow.plan_hash
    assert audit.verify_chain()

    stale = issue_approval(
        workflow_id=workflow.workflow_id,
        approver="alice@example.com",
        plan_hash="sha256:wrong-plan",
        secret="secret",
        now=1000,
    )
    try:
        workflows.approve_plan(workflow_id=workflow.workflow_id, approval=stale, secret="secret", now=1001)
        assert False, "stale approval must be rejected"
    except PermissionError:
        pass

    valid = issue_approval(
        workflow_id=workflow.workflow_id,
        approver="alice@example.com",
        plan_hash=workflow.plan_hash,
        secret="secret",
        now=1000,
    )
    approved = workflows.approve_plan(
        workflow_id=workflow.workflow_id,
        approval=valid,
        secret="secret",
        now=1001,
    )
    assert approved.status.value == "executing"
    assert approved.version == 2
    assert audit.verify_chain()
