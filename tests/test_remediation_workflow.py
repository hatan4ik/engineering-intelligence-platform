"""The opt-in Temporal remediation workflow: contracts, gating, and decisions.

The time-skipping Temporal test server is not assumed to be available offline,
so the workflow's decision logic and every activity are exercised here as plain
functions. ``tests/test_remediation_workflow_temporal.py`` runs the same
workflow end to end when a test-server binary is already cached locally.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

pytest.importorskip("temporalio")

from intelligence.incidents import EvidenceEvent, EvidenceKind
from orchestration.approvals import issue_approval
from orchestration.control_plane_activities import ControlPlaneActivityBridge, RemediationActivities
from orchestration.remediation_workflow import (
    ActionOutcome,
    ApprovalVerification,
    PolicyVerdict,
    RehearsalVerdict,
    RemediationApprovalSignal,
    RemediationPlanResult,
    RemediationRequest,
    RemediationWorkflowsDisabled,
    decide_after_approval,
    decide_after_plan,
    decide_after_policy,
    decide_after_rehearsal,
    evaluate_approval_signal,
    remediation_registration,
    remediation_workflows_enabled,
    terminal_status_for_action,
)
from remediation.catalog import AutonomyLevel, default_catalog
from remediation.executor import ExecutionResult
from remediation.opa_policy import EvaluatedPolicyDecision
from remediation.policy import PolicyDecision, ServiceAutonomy
from remediation.simulation import SimulationResult
from state.audit import SqliteAuditLog
from state.models import WorkflowStatus
from state.store import SqliteStateStore


ENABLED = {"EIP_TEMPORAL_REMEDIATION_WORKFLOWS": "enabled"}
SECRET = "approval-secret"


def request() -> RemediationRequest:
    return RemediationRequest(
        request_id="payments-crashloop-42",
        incident_id="incident-42",
        service="payments",
        environment="prod",
        correlation_id="corr-42",
        tenant_id="contoso",
        blast_radius=2,
    )


class FixtureEvidenceProvider:
    def __init__(self, events: tuple[EvidenceEvent, ...]) -> None:
        self.events = events
        self.calls: list[tuple[str, str, str]] = []

    def evidence(self, *, incident_id: str, service: str, environment: str):
        self.calls.append((incident_id, service, environment))
        return self.events


def crashloop_evidence() -> tuple[EvidenceEvent, ...]:
    when = datetime(2026, 8, 26, 12, 0, tzinfo=timezone.utc)
    return (
        EvidenceEvent(
            id="k8s-1",
            kind=EvidenceKind.K8S_EVENT,
            service="payments",
            timestamp=when,
            summary="Back-off restarting failed container: CrashLoopBackOff",
            source="kubernetes",
            severity=4,
            attributes=(("namespace", "payments"),),
        ),
        EvidenceEvent(
            id="alert-1",
            kind=EvidenceKind.ALERT,
            service="payments",
            timestamp=when,
            summary="availability below objective",
            source="azure-monitor",
            severity=4,
        ),
    )


class FakeAdapter:
    def __init__(self, *, verified: bool = True) -> None:
        self.verified = verified
        self.executed: list[str] = []
        self.rolled_back: list[str] = []

    def preflight(self, runbook, req):
        return True, "preconditions satisfied in test fixture"

    def execute(self, runbook_id, req):
        self.executed.append(runbook_id)
        return f"exec:{runbook_id}"

    def verify(self, signal, req):
        return self.verified

    def rollback(self, rollback_id, req):
        self.rolled_back.append(rollback_id)
        return f"rollback:{rollback_id}"


class AllowEvaluator:
    def evaluate(self, **kwargs):
        self.seen = kwargs
        return EvaluatedPolicyDecision(True, "authorized by fake OPA", "test-revision")


class DenyEvaluator:
    def evaluate(self, **kwargs):
        return EvaluatedPolicyDecision(False, "denied by fake OPA", "test-revision")


class FakeTwin:
    def __init__(self, *, safe: bool = True) -> None:
        self.safe = safe
        self.calls = 0

    def simulate(self, **kwargs):
        self.calls += 1
        status = "succeeded" if self.safe else "escalate"
        return SimulationResult(
            safe_to_promote=self.safe,
            execution=ExecutionResult(status=status, policy=PolicyDecision(True, "fake"), verified=self.safe),
            notes=("sandbox rehearsal",),
        )


def autonomy() -> ServiceAutonomy:
    return ServiceAutonomy(
        service="payments",
        environment="prod",
        level=AutonomyLevel.APPROVE_AND_EXECUTE,
        certified_runbooks=("aks.restart.crashloop",),
        max_blast_radius=3,
    )


def activities(tmp_path, *, environ=None, adapter=None, evaluator=None, twin=None):
    bridge = ControlPlaneActivityBridge(
        SqliteStateStore(tmp_path / "state.db"), SqliteAuditLog(tmp_path / "audit.db")
    )
    return RemediationActivities(
        bridge=bridge,
        catalog=default_catalog(),
        autonomy_policies=(autonomy(),),
        adapter=adapter or FakeAdapter(),
        evidence_provider=FixtureEvidenceProvider(crashloop_evidence()),
        approval_secret=SECRET,
        evaluator=evaluator or AllowEvaluator(),
        twin=twin or FakeTwin(),
        twin_source_namespace="payments",
        environ=dict(environ if environ is not None else ENABLED),
    )


# --- flag gating -------------------------------------------------------------

def test_flag_is_off_by_default():
    assert remediation_workflows_enabled({}) is False
    assert remediation_workflows_enabled({"EIP_TEMPORAL_REMEDIATION_WORKFLOWS": "true"}) is False
    assert remediation_workflows_enabled(ENABLED) is True


def test_every_activity_refuses_to_run_without_the_flag(tmp_path):
    acts = activities(tmp_path, environ={})
    req = request()
    with pytest.raises(RemediationWorkflowsDisabled):
        acts.collect_evidence(req)
    with pytest.raises(RemediationWorkflowsDisabled):
        acts.plan_remediation(req, None)
    with pytest.raises(RemediationWorkflowsDisabled):
        acts.execute_action(req, None, True)


def test_registration_requires_both_the_flag_and_cosmos_configuration():
    assert remediation_registration({}).registered is False
    flag_only = remediation_registration(
        {"EIP_CONTROL_PLANE_MODE": "temporal", **ENABLED}
    )
    assert flag_only.registered is False
    assert flag_only.flag_enabled is True
    assert "EIP_COSMOS_STATE_CONTAINER" in flag_only.missing_configuration
    ready = remediation_registration({
        "EIP_CONTROL_PLANE_MODE": "temporal",
        "EIP_COSMOS_ENDPOINT": "https://eip.documents.azure.invalid:443/",
        "EIP_COSMOS_DATABASE": "eip",
        "EIP_COSMOS_STATE_CONTAINER": "workflow-state",
        "EIP_COSMOS_AUDIT_CONTAINER": "workflow-audit",
        **ENABLED,
    })
    assert ready.registered is True
    assert ready.missing_configuration == ()


# --- approval signal ---------------------------------------------------------

def signal(*, plan_hash: str, workflow_id: str = "remediation:payments-crashloop-42") -> RemediationApprovalSignal:
    approval = issue_approval(
        workflow_id=workflow_id, approver="sre-oncall", plan_hash=plan_hash, secret=SECRET
    )
    return RemediationApprovalSignal(
        workflow_id=approval.workflow_id,
        approver=approval.approver,
        plan_hash=approval.plan_hash,
        issued_at=approval.issued_at,
        signature=approval.signature,
    )


def test_approval_signal_with_a_mismatched_plan_hash_is_rejected():
    decision = evaluate_approval_signal(
        expected_workflow_id="remediation:payments-crashloop-42",
        expected_plan_hash="sha256:" + "a" * 64,
        signal=signal(plan_hash="sha256:" + "b" * 64),
    )
    assert decision.accepted is False
    assert "plan hash" in decision.reason


def test_approval_signal_for_a_different_workflow_is_rejected():
    plan_hash = "sha256:" + "a" * 64
    decision = evaluate_approval_signal(
        expected_workflow_id="remediation:payments-crashloop-42",
        expected_plan_hash=plan_hash,
        signal=signal(plan_hash=plan_hash, workflow_id="remediation:someone-elses-plan"),
    )
    assert decision.accepted is False
    assert "workflow" in decision.reason


def test_matching_approval_signal_is_accepted():
    plan_hash = "sha256:" + "a" * 64
    decision = evaluate_approval_signal(
        expected_workflow_id="remediation:payments-crashloop-42",
        expected_plan_hash=plan_hash,
        signal=signal(plan_hash=plan_hash),
    )
    assert decision.accepted is True


def test_an_unsigned_signal_is_rejected_before_it_reaches_verification():
    plan_hash = "sha256:" + "a" * 64
    decision = evaluate_approval_signal(
        expected_workflow_id="remediation:payments-crashloop-42",
        expected_plan_hash=plan_hash,
        signal=RemediationApprovalSignal(
            workflow_id="remediation:payments-crashloop-42",
            approver="sre-oncall",
            plan_hash=plan_hash,
            issued_at=0,
            signature="",
        ),
    )
    assert decision.accepted is False


def test_a_forged_signature_fails_verification_in_the_activity(tmp_path):
    acts = activities(tmp_path)
    req = request()
    evidence = acts.collect_evidence(req)
    plan = acts.plan_remediation(req, evidence)
    forged = RemediationApprovalSignal(
        workflow_id=req.workflow_id,
        approver="sre-oncall",
        plan_hash=plan.plan_hash,
        issued_at=1,
        signature="0" * 64,
    )
    verification = acts.verify_approval(req, plan, forged)
    assert verification.verified is False


# --- decision logic ----------------------------------------------------------

def test_decision_logic_stops_on_every_negative_step():
    assert decide_after_plan(RemediationPlanResult(workflow_id="w", planned=False, reason="no runbook")).proceed is False
    assert decide_after_plan(
        RemediationPlanResult(workflow_id="w", planned=True, reason="ok", runbook_id="r", plan_hash="sha256:" + "a" * 64)
    ).proceed is True

    assert decide_after_approval(ApprovalVerification(verified=False, reason="bad signature")).proceed is False
    assert decide_after_approval(ApprovalVerification(verified=True, reason="ok", approver="sre")).proceed is True

    assert decide_after_policy(PolicyVerdict(allowed=False, reason="denied", policy_revision="r")).proceed is False
    assert decide_after_policy(PolicyVerdict(allowed=True, reason="ok", policy_revision="r")).proceed is True

    assert decide_after_rehearsal(RehearsalVerdict(safe_to_promote=False, status="escalate", notes=[])).proceed is False
    assert decide_after_rehearsal(RehearsalVerdict(safe_to_promote=True, status="succeeded", notes=[])).proceed is True


def test_denied_policy_is_terminal_and_never_reaches_execution():
    decision = decide_after_policy(PolicyVerdict(allowed=False, reason="denied", policy_revision="r"))
    assert decision.terminal_status == "denied"


def test_action_status_maps_to_a_terminal_workflow_status():
    assert terminal_status_for_action(ActionOutcome(status="succeeded", reason="")) == "succeeded"
    assert terminal_status_for_action(ActionOutcome(status="rolled_back", reason="")) == "rolled_back"
    assert terminal_status_for_action(ActionOutcome(status="escalate", reason="")) == "escalated"
    assert terminal_status_for_action(ActionOutcome(status="denied", reason="")) == "denied"
    assert terminal_status_for_action(ActionOutcome(status="anything-else", reason="")) == "failed"


# --- the activity sequence ---------------------------------------------------

def test_the_activity_sequence_persists_state_audit_and_a_bounded_action(tmp_path):
    adapter = FakeAdapter()
    twin = FakeTwin()
    acts = activities(tmp_path, adapter=adapter, twin=twin)
    req = request()

    evidence = acts.collect_evidence(req)
    assert evidence.evidence_ids == ["k8s-1", "alert-1"]

    plan = acts.plan_remediation(req, evidence)
    assert plan.planned is True
    assert plan.runbook_id == "aks.restart.crashloop"
    assert plan.plan_hash.startswith("sha256:")

    verification = acts.verify_approval(req, plan, signal(plan_hash=plan.plan_hash))
    assert verification.verified is True
    assert verification.approver == "sre-oncall"

    verdict = acts.evaluate_policy(req, plan, True)
    assert verdict.allowed is True

    rehearsal = acts.rehearse_in_twin(req, plan, True)
    assert rehearsal.safe_to_promote is True
    assert twin.calls == 1

    outcome = acts.execute_action(req, plan, True)
    assert outcome.status == "succeeded"
    assert adapter.executed == ["aks.restart.crashloop"]

    final = acts.record_outcome(req, plan, outcome, verification.approver)
    assert final.status == "succeeded"
    assert final.audit_event_hash

    record = acts.bridge.state.get_workflow(req.workflow_id)
    assert record.status is WorkflowStatus.SUCCEEDED
    assert record.plan_hash == plan.plan_hash
    assert acts.bridge.audit.verify_chain() is True


def test_policy_denial_never_calls_the_action_adapter(tmp_path):
    adapter = FakeAdapter()
    acts = activities(tmp_path, adapter=adapter, evaluator=DenyEvaluator())
    req = request()
    plan = acts.plan_remediation(req, acts.collect_evidence(req))
    verdict = acts.evaluate_policy(req, plan, True)
    assert verdict.allowed is False
    assert decide_after_policy(verdict).proceed is False
    assert adapter.executed == []


def test_the_mutation_boundary_refuses_an_unverified_approval(tmp_path):
    adapter = FakeAdapter()
    acts = activities(tmp_path, adapter=adapter)
    req = request()
    plan = acts.plan_remediation(req, acts.collect_evidence(req))
    outcome = acts.execute_action(req, plan, False)
    assert outcome.status == "denied"
    assert "verified human approval" in outcome.reason
    assert adapter.executed == []


def test_repeating_an_activity_does_not_advance_state_twice(tmp_path):
    acts = activities(tmp_path)
    req = request()
    stamp = "2026-08-26T12:00:00+00:00"
    first = acts.collect_evidence(req, stamp)
    replay = acts.collect_evidence(req, stamp)
    assert first.workflow_version == replay.workflow_version == 1
    assert first.audit_event_hash == replay.audit_event_hash
