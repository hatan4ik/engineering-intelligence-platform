from orchestration.approvals import issue_approval, verify_approval
from orchestration.state import WorkflowState, WorkflowStatus


def test_approval_is_bound_to_exact_plan_and_expires():
    approval = issue_approval(
        workflow_id="wf-1", approver="alice@example.com", plan_hash="plan-a", secret="test-secret", now=1000
    )
    assert verify_approval(
        approval,
        expected_workflow_id="wf-1",
        expected_plan_hash="plan-a",
        secret="test-secret",
        now=1100,
    )
    assert not verify_approval(
        approval,
        expected_workflow_id="wf-1",
        expected_plan_hash="plan-b",
        secret="test-secret",
        now=1100,
    )
    assert not verify_approval(
        approval,
        expected_workflow_id="wf-1",
        expected_plan_hash="plan-a",
        secret="test-secret",
        now=2000,
    )


def test_workflow_transition_is_explicit_and_inspectable():
    state = WorkflowState("wf-1", "payments", "prod", "plan-a")
    waiting = state.transition(status=WorkflowStatus.WAITING_APPROVAL, step="policy-approved")
    assert waiting.status == WorkflowStatus.WAITING_APPROVAL
    assert waiting.attempts == 1
