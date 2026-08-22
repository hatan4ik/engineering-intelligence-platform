from datetime import datetime, timedelta, timezone

import pytest

from control_plane.remediation import RemediationWorkflows
from intelligence.incidents import EvidenceEvent, EvidenceKind, analyze_incident
from orchestration.approvals import issue_approval
from orchestration.jobs import SqliteJobQueue
from orchestration.runner import DurableRunner
from product.durable_self_healing import DurableSelfHealingCoordinator
from remediation.catalog import AutonomyLevel, default_catalog
from remediation.policy import ServiceAutonomy
from resilience.certification import certify_l4_policy
from resilience.policy import AutonomyCertification
from state.audit import SqliteAuditLog
from state.store import SqliteStateStore


class Adapter:
    def __init__(self, verify=True):
        self.verify_result = verify
        self.calls = []
    def execute(self, runbook_id, request):
        self.calls.append(("execute", runbook_id))
        return "exec-1"
    def verify(self, signal, request):
        self.calls.append(("verify", signal))
        return self.verify_result
    def rollback(self, rollback_id, request):
        self.calls.append(("rollback", rollback_id))
        return "rollback-1"


def analysis():
    deployed = datetime(2026, 8, 22, 10, 0, tzinfo=timezone.utc)
    return analyze_incident([
        EvidenceEvent("deploy", EvidenceKind.DEPLOYMENT, "payments", deployed, "release", "ado", 1),
        EvidenceEvent("alert", EvidenceKind.ALERT, "payments", deployed + timedelta(minutes=2), "readiness failures", "monitor", 4),
    ], service="payments")


def l3_policy():
    return ServiceAutonomy("payments", "prod", AutonomyLevel.APPROVE_AND_EXECUTE, ("aks.rollout.undo",), 3)


def test_plan_bound_approval_enqueues_and_completes_after_restart(tmp_path):
    store = SqliteStateStore(tmp_path / "state.db")
    audit = SqliteAuditLog(tmp_path / "audit.db")
    queue = SqliteJobQueue(tmp_path / "jobs.db")
    prod, sandbox = Adapter(), Adapter()
    coordinator = DurableSelfHealingCoordinator(
        workflows=RemediationWorkflows(store, audit), queue=queue, catalog=default_catalog(),
        policy=l3_policy(), adapter=prod, sandbox_adapter=sandbox, approval_secret="secret",
    )
    prepared = coordinator.prepare(analysis(), incident_id="inc-1", blast_radius=2)
    assert prepared is not None and prepared.workflow.plan_hash
    approval = issue_approval(workflow_id=prepared.workflow.workflow_id, approver="sre@example", plan_hash=prepared.workflow.plan_hash, secret="secret", now=1000)
    assert coordinator.approve_and_enqueue(prepared, approval=approval, now=1000)

    runner = DurableRunner(queue, {coordinator.JOB_KIND: coordinator.handle_job})
    assert runner.run_once(now=1001) == "completed"
    assert store.get_workflow(prepared.workflow.workflow_id).status.value == "succeeded"
    assert audit.verify_chain() is True
    assert prod.calls[0] == ("execute", "aks.rollout.undo")


def test_wrong_plan_approval_never_enqueues(tmp_path):
    store = SqliteStateStore(tmp_path / "state.db")
    audit = SqliteAuditLog(tmp_path / "audit.db")
    queue = SqliteJobQueue(tmp_path / "jobs.db")
    coordinator = DurableSelfHealingCoordinator(
        workflows=RemediationWorkflows(store, audit), queue=queue, catalog=default_catalog(),
        policy=l3_policy(), adapter=Adapter(), sandbox_adapter=Adapter(), approval_secret="secret",
    )
    prepared = coordinator.prepare(analysis(), incident_id="inc-2", blast_radius=2)
    approval = issue_approval(workflow_id=prepared.workflow.workflow_id, approver="sre@example", plan_hash="sha256:wrong", secret="secret", now=1000)
    with pytest.raises(PermissionError):
        coordinator.approve_and_enqueue(prepared, approval=approval, now=1000)
    assert queue.claim(now=1001) is None


def test_l4_policy_requires_complete_exact_certification():
    policy = ServiceAutonomy("payments", "prod", AutonomyLevel.BOUNDED_AUTONOMOUS, ("aks.rollout.undo",), 2)
    certification = AutonomyCertification(
        service="payments", environment="prod", runbook_id="aks.rollout.undo", max_blast_radius=2,
        rollback_tested=True, kill_switch_tested=True, verification_independent=True, security_reviewed=True,
        error_budget_enforced=True, policy_fail_closed_tested=True, audit_fail_closed_tested=True,
        successful_exercises=3,
    )
    certify_l4_policy(policy, certification)

    incomplete = AutonomyCertification(
        service="payments", environment="prod", runbook_id="aks.rollout.undo", max_blast_radius=2,
        rollback_tested=True, kill_switch_tested=False, verification_independent=True, security_reviewed=True,
        error_budget_enforced=True, policy_fail_closed_tested=True, audit_fail_closed_tested=True,
        successful_exercises=3,
    )
    with pytest.raises(PermissionError):
        certify_l4_policy(policy, incomplete)
