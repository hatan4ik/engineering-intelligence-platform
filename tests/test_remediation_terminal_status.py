import pytest

from control_plane.remediation import RemediationTerminalStatus, workflow_status_for_terminal
from product.durable_self_healing import _terminal_status
from state.models import WorkflowStatus


def test_every_terminal_remediation_status_has_an_explicit_workflow_mapping():
    assert {
        status: workflow_status_for_terminal(status) for status in RemediationTerminalStatus
    } == {
        RemediationTerminalStatus.BLOCKED: WorkflowStatus.FAILED,
        RemediationTerminalStatus.DENIED: WorkflowStatus.FAILED,
        RemediationTerminalStatus.SUCCEEDED: WorkflowStatus.SUCCEEDED,
        RemediationTerminalStatus.ROLLED_BACK: WorkflowStatus.ROLLED_BACK,
        RemediationTerminalStatus.ESCALATE: WorkflowStatus.ESCALATED,
        RemediationTerminalStatus.FAILED: WorkflowStatus.FAILED,
    }


def test_durable_execution_boundary_rejects_unknown_terminal_status():
    with pytest.raises(ValueError, match="unknown remediation execution status"):
        _terminal_status("half-complete")
