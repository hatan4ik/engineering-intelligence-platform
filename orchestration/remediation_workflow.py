"""Opt-in Temporal remediation workflow: contracts, gating, and decision logic.

ADR-001 keeps the deployed worker evidence-only. This module adds the durable
remediation control loop that a *separately configured* worker may register:

    evidence -> plan -> wait for human approval -> policy (OPA) -> twin
    rehearsal -> action -> verify -> rollback/escalate -> audit

Every consequential step is an activity that refuses to run unless
``EIP_TEMPORAL_REMEDIATION_WORKFLOWS=enabled``; the worker registers this
workflow only when that flag is set *and* the state factory can build Cosmos
state and audit (:func:`remediation_registration`). A default deployment
therefore behaves exactly as before.

The approval wait is a Temporal signal carrying the exact plan hash. A signal
naming a different workflow or a different plan is rejected without advancing
the workflow, and acceptance of the hash is only the first gate: the signature
is separately verified by an activity before the plan reaches policy or
execution, so a raw token can never satisfy the human-approval gate.

Only the standard library and ``temporalio`` are imported here so the workflow
definition stays inside Temporal's determinism sandbox. The activity
implementations live in :mod:`orchestration.control_plane_activities` and are
referenced by name.
"""

from __future__ import annotations

import asyncio
import os
import re
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Callable, Mapping, Protocol

from temporalio import workflow
from temporalio.common import RetryPolicy


REMEDIATION_WORKFLOWS_FLAG = "EIP_TEMPORAL_REMEDIATION_WORKFLOWS"
REMEDIATION_WORKFLOW_NAME = "eip.remediation.v1"
APPROVAL_SIGNAL_NAME = "eip.remediation.approve.v1"
REJECTED_APPROVALS_QUERY = "eip.remediation.rejected-approvals.v1"

COLLECT_EVIDENCE_ACTIVITY = "eip.remediation.collect-evidence.v1"
PLAN_ACTIVITY = "eip.remediation.plan.v1"
VERIFY_APPROVAL_ACTIVITY = "eip.remediation.verify-approval.v1"
EVALUATE_POLICY_ACTIVITY = "eip.remediation.evaluate-policy.v1"
REHEARSE_ACTIVITY = "eip.remediation.rehearse.v1"
EXECUTE_ACTION_ACTIVITY = "eip.remediation.execute-action.v1"
RECORD_OUTCOME_ACTIVITY = "eip.remediation.record-outcome.v1"

_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_PLAN_HASH = re.compile(r"^sha256:[a-f0-9]{64}$")


class RemediationWorkflowsDisabled(RuntimeError):
    """A consequential remediation activity ran without its explicit opt-in flag."""


def remediation_workflows_enabled(environ: Mapping[str, str] | None = None) -> bool:
    source = os.environ if environ is None else environ
    return str(source.get(REMEDIATION_WORKFLOWS_FLAG, "")).strip().lower() == "enabled"


def require_remediation_workflows(
    step: str, environ: Mapping[str, str] | None = None
) -> None:
    if not remediation_workflows_enabled(environ):
        raise RemediationWorkflowsDisabled(
            f"{step} is a consequential remediation activity; set "
            f"{REMEDIATION_WORKFLOWS_FLAG}=enabled to register it"
        )


ActivityFunction = Callable[..., object]


class RemediationActivityProvider(Protocol):
    """Anything that can supply this workflow's registered activity functions."""

    def activity_functions(self) -> list[ActivityFunction]: ...


@dataclass(frozen=True)
class RemediationRegistration:
    """Whether the worker may register the remediation workflow, and why not."""

    registered: bool
    flag_enabled: bool
    missing_configuration: tuple[str, ...]
    reason: str


def remediation_registration(
    environ: Mapping[str, str] | None = None,
) -> RemediationRegistration:
    """Decide whether the worker may register ``eip.remediation.v1``.

    The gate is the factory's own predicate, not a variable-name check: the
    presence of the four ``EIP_COSMOS_*`` names says nothing about which backend
    :func:`state.factory.build_state_store` would actually return. In
    ``reference`` mode it returns SQLite regardless of how much Cosmos
    configuration is present, and a durable remediation workflow must never run
    on the reference backends.
    """
    # Imported lazily: state.factory pulls in the Azure SDK, which must not be a
    # module-level import of a workflow-definition module.
    from control_plane.runtime import TEMPORAL_MODE, control_plane_mode
    from state.factory import cosmos_backends_available, missing_cosmos_configuration

    source = os.environ if environ is None else environ
    enabled = remediation_workflows_enabled(source)
    if not enabled:
        return RemediationRegistration(
            registered=False,
            flag_enabled=False,
            missing_configuration=(),
            reason=f"{REMEDIATION_WORKFLOWS_FLAG} is not enabled; the worker stays evidence-only",
        )
    if cosmos_backends_available(source):
        return RemediationRegistration(
            registered=True,
            flag_enabled=True,
            missing_configuration=(),
            reason="flag enabled and the state factory builds Cosmos state and audit",
        )
    missing = missing_cosmos_configuration(source)
    mode = control_plane_mode(source)
    if mode != TEMPORAL_MODE:
        return RemediationRegistration(
            registered=False,
            flag_enabled=True,
            missing_configuration=missing,
            reason=(
                f"EIP_CONTROL_PLANE_MODE={mode} builds the reference SQLite backends, not Cosmos "
                f"state and audit; remediation workflows require {TEMPORAL_MODE} mode"
            ),
        )
    return RemediationRegistration(
        registered=False,
        flag_enabled=True,
        missing_configuration=missing,
        reason="Cosmos state and audit configuration is incomplete; missing: "
        + ", ".join(missing),
    )


# --- workflow data contracts -------------------------------------------------


@dataclass
class RemediationRequest:
    request_id: str
    incident_id: str
    service: str
    environment: str
    correlation_id: str
    tenant_id: str = "default"
    blast_radius: int = 1
    approval_timeout_seconds: int = 3600

    def validate(self) -> None:
        for label, value in (
            ("request_id", self.request_id),
            ("incident_id", self.incident_id),
            ("service", self.service),
            ("environment", self.environment),
            ("correlation_id", self.correlation_id),
            ("tenant_id", self.tenant_id),
        ):
            if not _IDENTIFIER.fullmatch(str(value)):
                raise ValueError(f"{label} must be a bounded opaque identifier")
        if self.blast_radius < 0:
            raise ValueError("blast_radius must not be negative")
        if self.approval_timeout_seconds <= 0:
            raise ValueError("approval_timeout_seconds must be positive")

    @property
    def workflow_id(self) -> str:
        self.validate()
        return f"remediation:{self.request_id}"


@dataclass
class EvidenceBundle:
    workflow_id: str
    workflow_version: int
    evidence: list[dict] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)
    audit_event_hash: str = ""


@dataclass
class RemediationPlanResult:
    workflow_id: str
    planned: bool
    reason: str
    runbook_id: str | None = None
    plan_hash: str | None = None
    confidence: float = 0.0
    evidence_ids: list[str] = field(default_factory=list)
    workflow_version: int = 0


@dataclass
class RemediationApprovalSignal:
    """A human approval delivered as a Temporal signal, bound to one plan hash."""

    workflow_id: str
    approver: str
    plan_hash: str
    issued_at: int
    signature: str


@dataclass(frozen=True)
class ApprovalSignalDecision:
    accepted: bool
    reason: str


def evaluate_approval_signal(
    *,
    expected_workflow_id: str,
    expected_plan_hash: str | None,
    signal: RemediationApprovalSignal,
) -> ApprovalSignalDecision:
    """Deterministic, side-effect-free admission check for an approval signal.

    This runs inside the workflow, so it never touches the approval secret. It
    rejects a signal that is not bound to this workflow and this exact plan
    hash; a signal that passes here is still only a *candidate* until the
    verification activity checks its signature.
    """
    if not expected_plan_hash or not _PLAN_HASH.fullmatch(expected_plan_hash):
        return ApprovalSignalDecision(
            False, "there is no approved plan hash to approve against"
        )
    if signal.workflow_id != expected_workflow_id:
        return ApprovalSignalDecision(False, "approval names a different workflow")
    if signal.plan_hash != expected_plan_hash:
        return ApprovalSignalDecision(
            False, "approval plan hash does not match the planned remediation"
        )
    if not str(signal.approver).strip():
        return ApprovalSignalDecision(False, "approval does not name an approver")
    if not str(signal.signature).strip():
        return ApprovalSignalDecision(False, "approval carries no signature to verify")
    return ApprovalSignalDecision(
        True, "approval is bound to this workflow and plan hash"
    )


@dataclass
class ApprovalVerification:
    verified: bool
    reason: str
    approver: str = ""


@dataclass
class PolicyVerdict:
    allowed: bool
    reason: str
    policy_revision: str


@dataclass
class RehearsalVerdict:
    safe_to_promote: bool
    status: str
    notes: list[str] = field(default_factory=list)


@dataclass
class ActionOutcome:
    status: str
    reason: str
    execution_ref: str | None = None
    verified: bool = False
    rollback_ref: str | None = None
    error: str | None = None
    # The lifecycle predecessor the terminal transition must compare-and-swap
    # against. Carried in the payload so an activity retry rebuilds an
    # identical lifecycle event.
    from_status: str = "received"
    workflow_version: int = 0


@dataclass
class RemediationOutcome:
    workflow_id: str
    status: str
    reason: str
    plan_hash: str | None = None
    approver: str = ""
    execution_ref: str | None = None
    rollback_ref: str | None = None
    audit_event_hash: str = ""
    mutation_attempted: bool = False


# --- decision logic (pure) ---------------------------------------------------


@dataclass(frozen=True)
class StepDecision:
    proceed: bool
    terminal_status: str
    reason: str


_PROCEED = StepDecision(True, "", "")


def decide_after_plan(plan: RemediationPlanResult) -> StepDecision:
    if not plan.planned or not plan.runbook_id or not plan.plan_hash:
        return StepDecision(
            False,
            "escalate",
            plan.reason or "no certified runbook matched the evidence",
        )
    return _PROCEED


def decide_after_approval(verification: ApprovalVerification) -> StepDecision:
    if not verification.verified:
        return StepDecision(
            False,
            "escalate",
            verification.reason or "human approval could not be verified",
        )
    return _PROCEED


def decide_after_policy(verdict: PolicyVerdict) -> StepDecision:
    if not verdict.allowed:
        return StepDecision(
            False, "denied", verdict.reason or "policy denied the remediation"
        )
    return _PROCEED


def decide_after_rehearsal(rehearsal: RehearsalVerdict) -> StepDecision:
    if not rehearsal.safe_to_promote:
        return StepDecision(
            False,
            "escalate",
            "digital-twin rehearsal did not verify; production promotion stays blocked",
        )
    return _PROCEED


_TERMINAL_STATUS = {
    "succeeded": "succeeded",
    "rolled_back": "rolled_back",
    "escalate": "escalated",
    "escalated": "escalated",
    "denied": "denied",
}


def terminal_status_for_action(outcome: ActionOutcome) -> str:
    return _TERMINAL_STATUS.get(outcome.status, "failed")


# --- the workflow ------------------------------------------------------------


_STEP_RETRY = RetryPolicy(
    maximum_attempts=5,
    non_retryable_error_types=[
        "RemediationWorkflowsDisabled",
        "RemediationConfigurationError",
        "ValueError",
        "LifecycleContractError",
    ],
)
# A mutation is never retried automatically: a second attempt would be a second
# production action against evidence that is no longer known to hold.
_ACTION_RETRY = RetryPolicy(
    maximum_attempts=1,
    non_retryable_error_types=[
        "RemediationWorkflowsDisabled",
        "RemediationConfigurationError",
    ],
)
_STEP_TIMEOUT = timedelta(minutes=5)
_ACTION_TIMEOUT = timedelta(minutes=15)


@workflow.defn(name=REMEDIATION_WORKFLOW_NAME)
class RemediationWorkflow:
    """The durable control loop. Consequential steps live in activities."""

    def __init__(self) -> None:
        self._pending: list[RemediationApprovalSignal] = []
        self._rejected: list[str] = []

    @workflow.signal(name=APPROVAL_SIGNAL_NAME)
    def submit_approval(self, signal: RemediationApprovalSignal) -> None:
        self._pending.append(signal)

    @workflow.query(name=REJECTED_APPROVALS_QUERY)
    def rejected_approvals(self) -> list[str]:
        return list(self._rejected)

    @workflow.run
    async def run(self, request: RemediationRequest) -> RemediationOutcome:
        evidence: EvidenceBundle = await workflow.execute_activity(
            COLLECT_EVIDENCE_ACTIVITY,
            args=[request, self._now()],
            result_type=EvidenceBundle,
            start_to_close_timeout=_STEP_TIMEOUT,
            retry_policy=_STEP_RETRY,
        )
        plan: RemediationPlanResult = await workflow.execute_activity(
            PLAN_ACTIVITY,
            args=[request, evidence, self._now()],
            result_type=RemediationPlanResult,
            start_to_close_timeout=_STEP_TIMEOUT,
            retry_policy=_STEP_RETRY,
        )
        decision = decide_after_plan(plan)
        if not decision.proceed:
            return await self._finish(
                request, plan, decision, "", "received", evidence.workflow_version
            )

        signal = await self._await_approval(request, plan)
        if signal is None:
            return await self._finish(
                request,
                plan,
                StepDecision(
                    False,
                    "escalate",
                    "no valid human approval was received before the approval deadline",
                ),
                "",
                "waiting_approval",
                plan.workflow_version,
            )

        verification: ApprovalVerification = await workflow.execute_activity(
            VERIFY_APPROVAL_ACTIVITY,
            args=[request, plan, signal],
            result_type=ApprovalVerification,
            start_to_close_timeout=_STEP_TIMEOUT,
            retry_policy=_STEP_RETRY,
        )
        decision = decide_after_approval(verification)
        if not decision.proceed:
            return await self._finish(
                request, plan, decision, "", "waiting_approval", plan.workflow_version
            )

        verdict: PolicyVerdict = await workflow.execute_activity(
            EVALUATE_POLICY_ACTIVITY,
            args=[request, plan, True],
            result_type=PolicyVerdict,
            start_to_close_timeout=_STEP_TIMEOUT,
            retry_policy=_STEP_RETRY,
        )
        decision = decide_after_policy(verdict)
        if not decision.proceed:
            return await self._finish(
                request,
                plan,
                decision,
                verification.approver,
                "waiting_approval",
                plan.workflow_version,
            )

        rehearsal: RehearsalVerdict = await workflow.execute_activity(
            REHEARSE_ACTIVITY,
            args=[request, plan, True],
            result_type=RehearsalVerdict,
            start_to_close_timeout=_ACTION_TIMEOUT,
            retry_policy=_STEP_RETRY,
        )
        decision = decide_after_rehearsal(rehearsal)
        if not decision.proceed:
            return await self._finish(
                request,
                plan,
                decision,
                verification.approver,
                "waiting_approval",
                plan.workflow_version,
            )

        outcome: ActionOutcome = await workflow.execute_activity(
            EXECUTE_ACTION_ACTIVITY,
            args=[request, plan, True, self._now()],
            result_type=ActionOutcome,
            start_to_close_timeout=_ACTION_TIMEOUT,
            retry_policy=_ACTION_RETRY,
        )
        return await self._record(request, plan, outcome, verification.approver)

    def _now(self) -> str:
        """Replay-safe step timestamp.

        Activity retries must reuse the same lifecycle-event fingerprint, so the
        timestamp is fixed by the workflow rather than read inside the activity.
        """
        return workflow.now().isoformat()

    async def _await_approval(
        self, request: RemediationRequest, plan: RemediationPlanResult
    ) -> RemediationApprovalSignal | None:
        deadline = workflow.now() + timedelta(seconds=request.approval_timeout_seconds)
        while True:
            remaining = deadline - workflow.now()
            if remaining <= timedelta(0):
                return None
            try:
                await workflow.wait_condition(
                    lambda: bool(self._pending), timeout=remaining
                )
            except asyncio.TimeoutError:
                return None
            while self._pending:
                candidate = self._pending.pop(0)
                decision = evaluate_approval_signal(
                    expected_workflow_id=request.workflow_id,
                    expected_plan_hash=plan.plan_hash,
                    signal=candidate,
                )
                if decision.accepted:
                    return candidate
                self._rejected.append(decision.reason)

    async def _finish(
        self,
        request: RemediationRequest,
        plan: RemediationPlanResult,
        decision: StepDecision,
        approver: str,
        from_status: str,
        workflow_version: int,
    ) -> RemediationOutcome:
        return await self._record(
            request,
            plan,
            ActionOutcome(
                status=decision.terminal_status,
                reason=decision.reason,
                from_status=from_status,
                workflow_version=workflow_version,
            ),
            approver,
        )

    async def _record(
        self,
        request: RemediationRequest,
        plan: RemediationPlanResult,
        outcome: ActionOutcome,
        approver: str,
    ) -> RemediationOutcome:
        return await workflow.execute_activity(
            RECORD_OUTCOME_ACTIVITY,
            args=[request, plan, outcome, approver, self._now()],
            result_type=RemediationOutcome,
            start_to_close_timeout=_STEP_TIMEOUT,
            retry_policy=_STEP_RETRY,
        )
