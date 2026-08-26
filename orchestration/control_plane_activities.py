"""Fail-closed Temporal activity boundary for authoritative lifecycle events.

This module is deliberately not registered by the evidence worker.  It is the
next product-control-plane slice: once a separately configured worker is
introduced, every consequential workflow transition must pass through this
state-and-audit boundary before the workflow can advance.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime
from collections.abc import Mapping as AbcMapping
from pathlib import Path
from typing import Mapping, Protocol

from temporalio import activity

# Private on purpose: the remediation plan hash must stay byte-identical to the
# one control_plane.remediation writes, so both are computed by one helper.
from control_plane.remediation import RemediationWorkflowPlan, _hash as _plan_hash
from intelligence.incidents import EvidenceEvent, EvidenceKind, analyze_incident
from orchestration.approvals import Approval, verify_approval
from orchestration.remediation_workflow import (
    COLLECT_EVIDENCE_ACTIVITY,
    EVALUATE_POLICY_ACTIVITY,
    EXECUTE_ACTION_ACTIVITY,
    PLAN_ACTIVITY,
    RECORD_OUTCOME_ACTIVITY,
    REHEARSE_ACTIVITY,
    VERIFY_APPROVAL_ACTIVITY,
    ActionOutcome,
    ApprovalVerification,
    EvidenceBundle,
    PolicyVerdict,
    RehearsalVerdict,
    RemediationApprovalSignal,
    RemediationPlanResult,
    RemediationRequest,
    RemediationOutcome,
    require_remediation_workflows,
    terminal_status_for_action,
)
from remediation.catalog import AutonomyLevel, RunbookCatalog, default_catalog
from remediation.digital_twin import KubernetesDigitalTwin
from remediation.executor import ActionAdapter, execute_control_loop
from remediation.kubernetes_adapter import KubernetesActionAdapter
from remediation.opa_policy import OpaPolicyClient, PolicyControlState, PolicyEvaluator
from remediation.planner import plan_from_incident
from remediation.policy import ActionRequest, ServiceAutonomy
from remediation.simulation import SimulationResult
from state.audit import AuditLog
from state.lifecycle import WorkflowLifecycleEvent
from state.models import AuditEvent, WorkflowRecord, WorkflowStatus
from state.store import StateStore


class AuditExportFailure(RuntimeError):
    """A lifecycle state change cannot be acknowledged without its audit export."""


@dataclass(frozen=True)
class WorkflowLifecycleActivityResult:
    workflow_id: str
    workflow_version: int
    status: str
    event_id: str
    idempotency_key: str
    state_replayed: bool
    audit_event_hash: str


class ControlPlaneActivityBridge:
    """Persist one lifecycle event and its audit record with retry-safe semantics.

    State is committed first together with an idempotency receipt. If audit
    export then fails, the activity raises and Temporal retries it. The retry
    resolves the receipt, does not advance state a second time, and attempts
    the same deterministic audit event again. A workflow must not schedule a
    consequential next step until this activity returns successfully.
    """

    def __init__(self, state: StateStore, audit: AuditLog) -> None:
        self.state = state
        self.audit = audit

    @activity.defn(name="eip.persist-workflow-lifecycle.v1")
    def persist_workflow_lifecycle(
        self, event: WorkflowLifecycleEvent
    ) -> WorkflowLifecycleActivityResult:
        transition = self.state.apply_workflow_event(event)
        audit_event = _audit_event(event, transition.record)
        try:
            exported = self.audit.append(audit_event)
        except Exception as exc:
            raise AuditExportFailure(
                "workflow lifecycle state was retained, but immutable audit export did not complete"
            ) from exc
        if not exported.event_hash:
            raise AuditExportFailure("audit exporter returned an event without a verifiable hash")
        return WorkflowLifecycleActivityResult(
            workflow_id=transition.record.workflow_id,
            workflow_version=transition.record.version,
            status=transition.record.status.value,
            event_id=event.event_id,
            idempotency_key=event.idempotency_key,
            state_replayed=transition.replayed,
            audit_event_hash=exported.event_hash,
        )


def _audit_event(event: WorkflowLifecycleEvent, record: WorkflowRecord) -> AuditEvent:
    return AuditEvent(
        event_id=f"workflow-lifecycle:{event.event_id}",
        correlation_id=event.correlation_id,
        actor=event.actor,
        action=event.action,
        resource=event.workflow_id,
        occurred_at=event.occurred_at,
        payload={
            "schema_version": event.schema_version,
            "event_id": event.event_id,
            "idempotency_key": event.idempotency_key,
            "causation_id": event.causation_id,
            "tenant_id": event.tenant_id,
            "service_id": event.service_id,
            "environment": event.environment,
            "kind": event.kind,
            "from_status": event.from_status.value if event.from_status else None,
            "to_status": event.to_status.value,
            "expected_version": event.expected_version,
            "resulting_version": record.version,
            "plan_hash": record.plan_hash,
            "consequential": event.consequential,
            "event_fingerprint": event.fingerprint,
            "attributes": dict(event.attributes),
        },
    )


# ---------------------------------------------------------------------------
# Opt-in remediation activities
#
# These are the consequential steps of `eip.remediation.v1`
# (orchestration.remediation_workflow).  Each one refuses to run unless
# EIP_TEMPORAL_REMEDIATION_WORKFLOWS=enabled, and each authoritative state
# change goes through ControlPlaneActivityBridge above, so no remediation step
# can advance without its audit export.
# ---------------------------------------------------------------------------


class RemediationConfigurationError(RuntimeError):
    """Remediation activities were requested without their required configuration."""


def _require_step_time(occurred_at: str) -> str:
    """The step timestamp must come from the caller, never from the clock here.

    An activity retry has to rebuild a byte-identical lifecycle event or its
    fingerprint stops matching the stored idempotency receipt. Reading the clock
    inside the activity would break that on every retry, so there is deliberately
    no fallback: the workflow supplies ``workflow.now()``, which is replay-safe.
    """
    value = str(occurred_at or "").strip()
    if not value:
        raise RemediationConfigurationError(
            "a persisting remediation activity requires a caller-supplied, replay-safe "
            "occurred_at timestamp"
        )
    return value


def evidence_to_mapping(event: EvidenceEvent) -> dict:
    return {
        "id": event.id,
        "kind": event.kind.value,
        "service": event.service,
        "timestamp": event.timestamp.isoformat(),
        "summary": event.summary,
        "source": event.source,
        "severity": event.severity,
        "attributes": [[key, value] for key, value in event.attributes],
    }


def evidence_from_mapping(raw: Mapping[str, object]) -> EvidenceEvent:
    return EvidenceEvent(
        id=str(raw["id"]),
        kind=EvidenceKind(str(raw["kind"])),
        service=str(raw["service"]),
        timestamp=datetime.fromisoformat(str(raw["timestamp"])),
        summary=str(raw["summary"]),
        source=str(raw["source"]),
        severity=int(raw.get("severity", 1)),
        attributes=tuple((str(k), str(v)) for k, v in (raw.get("attributes") or [])),
    )


class RehearsalTwin(Protocol):
    """The digital-twin sandbox a remediation plan is rehearsed in."""

    def simulate(
        self,
        *,
        simulation_id: str,
        source_namespace: str,
        catalog: RunbookCatalog,
        policy: ServiceAutonomy,
        request: ActionRequest,
        approval_verified: bool = False,
    ) -> SimulationResult: ...


class IncidentEvidenceProvider(Protocol):
    """Where a remediation workflow reads its incident evidence from."""

    def evidence(
        self, *, incident_id: str, service: str, environment: str
    ) -> tuple[EvidenceEvent, ...]: ...


class JsonFixtureEvidenceProvider:
    """Reads evidence from a reviewed JSON fixture.

    This is the only evidence source the worker can be configured with today.
    It exists so a rehearsal deployment is explicit about the fact that its
    evidence is a fixture, rather than silently pretending to observe
    production.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def evidence(
        self, *, incident_id: str, service: str, environment: str
    ) -> tuple[EvidenceEvent, ...]:
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        records = raw.get(incident_id) if isinstance(raw, AbcMapping) else raw
        if records is None:
            return ()
        return tuple(evidence_from_mapping(item) for item in records)


def load_service_autonomy(path: str | Path) -> tuple[ServiceAutonomy, ...]:
    """Load reviewed service autonomy policies from a JSON file.

    Autonomy levels and certified runbooks are reviewed product decisions. They
    are read from a file, never inferred, learned, or defaulted.
    """
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise RemediationConfigurationError("service autonomy file must contain a JSON list")
    policies = []
    for index, item in enumerate(raw):
        try:
            policies.append(
                ServiceAutonomy(
                    service=str(item["service"]),
                    environment=str(item["environment"]),
                    level=AutonomyLevel(int(item["level"])),
                    certified_runbooks=tuple(str(r) for r in item.get("certified_runbooks", ())),
                    max_blast_radius=int(item.get("max_blast_radius", 0)),
                    kill_switch=bool(item.get("kill_switch", False)),
                )
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise RemediationConfigurationError(
                f"service autonomy entry {index} is invalid: {exc}"
            ) from exc
    return tuple(policies)


_TERMINAL_WORKFLOW_STATUS = {
    "succeeded": WorkflowStatus.SUCCEEDED,
    "rolled_back": WorkflowStatus.ROLLED_BACK,
    "escalated": WorkflowStatus.ESCALATED,
    "denied": WorkflowStatus.FAILED,
    "failed": WorkflowStatus.FAILED,
}


class RemediationActivities:
    """The activity implementations behind ``eip.remediation.v1``.

    Every method is fail-closed: it raises :class:`RemediationWorkflowsDisabled`
    unless the opt-in flag is set, and every authoritative state change is
    written through :class:`ControlPlaneActivityBridge` so state and audit stay
    coupled.
    """

    def __init__(
        self,
        *,
        bridge: ControlPlaneActivityBridge,
        catalog: RunbookCatalog,
        autonomy_policies: tuple[ServiceAutonomy, ...],
        adapter: ActionAdapter,
        evidence_provider: IncidentEvidenceProvider,
        approval_secret: str,
        evaluator: PolicyEvaluator | None = None,
        twin: RehearsalTwin | None = None,
        twin_source_namespace: str | None = None,
        environ: Mapping[str, str] | None = None,
        actor: str = "agent:remediation-workflow",
    ) -> None:
        self.bridge = bridge
        self.catalog = catalog
        self.autonomy_policies = tuple(autonomy_policies)
        self.adapter = adapter
        self.evidence_provider = evidence_provider
        self.approval_secret = approval_secret
        self.evaluator = evaluator
        self.twin = twin
        self.twin_source_namespace = twin_source_namespace
        self.environ = environ
        self.actor = actor

    # -- registration -------------------------------------------------------

    def activity_functions(self) -> list[object]:
        return [
            self.collect_evidence,
            self.plan_remediation,
            self.verify_approval,
            self.evaluate_policy,
            self.rehearse_in_twin,
            self.execute_action,
            self.record_outcome,
        ]

    # -- helpers ------------------------------------------------------------

    def _autonomy(self, request: RemediationRequest) -> ServiceAutonomy:
        for policy in self.autonomy_policies:
            if policy.service == request.service and policy.environment == request.environment:
                return policy
        raise RemediationConfigurationError(
            f"no reviewed autonomy policy for {request.service}/{request.environment}"
        )

    def _advance(
        self,
        request: RemediationRequest,
        *,
        step: str,
        action: str,
        from_status: WorkflowStatus | None,
        expected_version: int | None,
        to_status: WorkflowStatus,
        occurred_at: str,
        plan_hash: str | None = None,
        attributes: Mapping[str, object] | None = None,
        consequential: bool = False,
    ) -> WorkflowLifecycleActivityResult:
        """Build one lifecycle event that is byte-identical across retries.

        The predecessor status and version are supplied by the caller (the
        workflow threads them forward from the previous committed step) rather
        than read from live state. Reading live state would make a retry after a
        successful commit produce a *different* event, whose fingerprint would
        no longer match the stored idempotency receipt.
        """
        event = WorkflowLifecycleEvent(
            event_id=f"{request.workflow_id}:{step}",
            idempotency_key=f"{request.workflow_id}:{step}",
            workflow_id=request.workflow_id,
            tenant_id=request.tenant_id,
            service_id=request.service,
            environment=request.environment,
            kind="remediation",
            correlation_id=request.correlation_id,
            actor=self.actor,
            action=action,
            from_status=from_status,
            to_status=to_status,
            expected_version=expected_version,
            plan_hash=plan_hash,
            consequential=consequential,
            attributes=dict(attributes or {}),
            occurred_at=occurred_at,
        )
        return self.bridge.persist_workflow_lifecycle(event)

    # -- activities ---------------------------------------------------------

    @activity.defn(name=COLLECT_EVIDENCE_ACTIVITY)
    def collect_evidence(self, request: RemediationRequest, occurred_at: str) -> EvidenceBundle:
        require_remediation_workflows("collect_evidence", self.environ)
        request.validate()
        events = tuple(
            self.evidence_provider.evidence(
                incident_id=request.incident_id,
                service=request.service,
                environment=request.environment,
            )
        )
        result = self._advance(
            request,
            step="evidence",
            action="collect-remediation-evidence",
            from_status=None,
            expected_version=None,
            to_status=WorkflowStatus.RECEIVED,
            occurred_at=_require_step_time(occurred_at),
            attributes={
                "incident_id": request.incident_id,
                "evidence_ids": [event.id for event in events],
            },
        )
        return EvidenceBundle(
            workflow_id=request.workflow_id,
            workflow_version=result.workflow_version,
            evidence=[evidence_to_mapping(event) for event in events],
            evidence_ids=[event.id for event in events],
            audit_event_hash=result.audit_event_hash,
        )

    @activity.defn(name=PLAN_ACTIVITY)
    def plan_remediation(
        self,
        request: RemediationRequest,
        evidence: EvidenceBundle | None,
        occurred_at: str,
    ) -> RemediationPlanResult:
        require_remediation_workflows("plan_remediation", self.environ)
        request.validate()
        if evidence is None:
            raise RemediationConfigurationError("plan_remediation requires an evidence bundle")
        events = [evidence_from_mapping(item) for item in evidence.evidence]
        analysis = analyze_incident(events, service=request.service)
        plan = plan_from_incident(analysis)
        if plan is None:
            return RemediationPlanResult(
                workflow_id=request.workflow_id,
                planned=False,
                reason="no certified runbook matched the incident evidence",
                evidence_ids=list(evidence.evidence_ids),
                workflow_version=evidence.workflow_version,
            )
        workflow_plan = RemediationWorkflowPlan(
            workflow_id=request.workflow_id,
            service=request.service,
            environment=request.environment,
            runbook_id=plan.runbook_id,
            blast_radius=request.blast_radius,
            evidence_ids=tuple(plan.evidence_ids),
            confidence=plan.confidence,
        )
        plan_hash = _plan_hash(workflow_plan.payload())
        planned = self._advance(
            request,
            step="planned",
            action="prepare-remediation",
            from_status=WorkflowStatus.RECEIVED,
            expected_version=evidence.workflow_version,
            to_status=WorkflowStatus.PLANNED,
            occurred_at=_require_step_time(occurred_at),
            plan_hash=plan_hash,
            attributes={**workflow_plan.payload(), "reason": plan.reason},
        )
        # The record enters WAITING_APPROVAL before the workflow blocks on the
        # signal, so an operator inspecting authoritative state sees why it is
        # waiting rather than an apparently stalled PLANNED workflow.
        waiting = self._advance(
            request,
            step="awaiting-approval",
            action="await-human-approval",
            from_status=WorkflowStatus.PLANNED,
            expected_version=planned.workflow_version,
            to_status=WorkflowStatus.WAITING_APPROVAL,
            occurred_at=_require_step_time(occurred_at),
            plan_hash=plan_hash,
            attributes={"plan_hash": plan_hash},
        )
        return RemediationPlanResult(
            workflow_id=request.workflow_id,
            planned=True,
            reason=plan.reason,
            runbook_id=plan.runbook_id,
            plan_hash=plan_hash,
            confidence=plan.confidence,
            evidence_ids=list(plan.evidence_ids),
            workflow_version=waiting.workflow_version,
        )

    @activity.defn(name=VERIFY_APPROVAL_ACTIVITY)
    def verify_approval(
        self,
        request: RemediationRequest,
        plan: RemediationPlanResult,
        signal: RemediationApprovalSignal,
    ) -> ApprovalVerification:
        require_remediation_workflows("verify_approval", self.environ)
        if not plan.plan_hash:
            return ApprovalVerification(False, "there is no plan hash to approve against")
        verified = verify_approval(
            Approval(
                workflow_id=signal.workflow_id,
                approver=signal.approver,
                plan_hash=signal.plan_hash,
                issued_at=int(signal.issued_at),
                signature=signal.signature,
            ),
            expected_workflow_id=request.workflow_id,
            expected_plan_hash=plan.plan_hash,
            secret=self.approval_secret,
        )
        if not verified:
            return ApprovalVerification(
                False, "approval is invalid, stale, expired, or bound to another plan"
            )
        return ApprovalVerification(True, "approval signature verified", signal.approver)

    @activity.defn(name=EVALUATE_POLICY_ACTIVITY)
    def evaluate_policy(
        self,
        request: RemediationRequest,
        plan: RemediationPlanResult,
        approval_verified: bool,
    ) -> PolicyVerdict:
        require_remediation_workflows("evaluate_policy", self.environ)
        if self.evaluator is None:
            return PolicyVerdict(False, "no policy evaluator is configured; failing closed", "unknown")
        if not plan.runbook_id:
            return PolicyVerdict(False, "there is no planned runbook to authorize", "unknown")
        evaluated = self.evaluator.evaluate(
            runbook=self.catalog.get(plan.runbook_id),
            policy=self._autonomy(request),
            request=self._action_request(request, plan),
            approval_verified=bool(approval_verified),
            control=PolicyControlState(),
        )
        return PolicyVerdict(
            allowed=bool(evaluated.allowed),
            reason=str(evaluated.reason),
            policy_revision=str(evaluated.policy_revision),
        )

    @activity.defn(name=REHEARSE_ACTIVITY)
    def rehearse_in_twin(
        self,
        request: RemediationRequest,
        plan: RemediationPlanResult,
        approval_verified: bool,
    ) -> RehearsalVerdict:
        require_remediation_workflows("rehearse_in_twin", self.environ)
        if self.twin is None or not self.twin_source_namespace:
            return RehearsalVerdict(False, "unconfigured", ["digital twin is not configured; failing closed"])
        if not plan.runbook_id:
            return RehearsalVerdict(False, "unplanned", ["there is no planned runbook to rehearse"])
        result = self.twin.simulate(
            simulation_id=request.request_id,
            source_namespace=self.twin_source_namespace,
            catalog=self.catalog,
            policy=self._autonomy(request),
            request=self._action_request(request, plan),
            approval_verified=bool(approval_verified),
        )
        return RehearsalVerdict(
            safe_to_promote=bool(result.safe_to_promote),
            status=result.execution.status,
            notes=list(result.notes),
        )

    @activity.defn(name=EXECUTE_ACTION_ACTIVITY)
    def execute_action(
        self,
        request: RemediationRequest,
        plan: RemediationPlanResult | None,
        approval_verified: bool,
        occurred_at: str,
    ) -> ActionOutcome:
        require_remediation_workflows("execute_action", self.environ)
        if plan is None or not plan.runbook_id:
            return ActionOutcome(
                status="denied",
                reason="there is no planned runbook to execute",
                from_status=WorkflowStatus.WAITING_APPROVAL.value,
                workflow_version=plan.workflow_version if plan else 0,
            )
        # Defence in depth: the workflow never reaches here without a verified
        # approval, but the mutation boundary refuses one regardless.
        if not approval_verified:
            return ActionOutcome(
                status="denied",
                reason="verified human approval is required before any mutation",
                from_status=WorkflowStatus.WAITING_APPROVAL.value,
                workflow_version=plan.workflow_version,
            )
        executing = self._advance(
            request,
            step="executing",
            action="execute-remediation",
            from_status=WorkflowStatus.WAITING_APPROVAL,
            expected_version=plan.workflow_version,
            to_status=WorkflowStatus.EXECUTING,
            occurred_at=_require_step_time(occurred_at),
            plan_hash=plan.plan_hash,
            attributes={"runbook_id": plan.runbook_id, "blast_radius": request.blast_radius},
            consequential=True,
        )
        result = execute_control_loop(
            catalog=self.catalog,
            policy=self._autonomy(request),
            request=self._action_request(request, plan),
            adapter=self.adapter,
            evaluator=self.evaluator,
            approval_verified=True,
        )
        verifying = self._advance(
            request,
            step="verifying",
            action="verify-remediation",
            from_status=WorkflowStatus.EXECUTING,
            expected_version=executing.workflow_version,
            to_status=WorkflowStatus.VERIFYING,
            occurred_at=_require_step_time(occurred_at),
            plan_hash=plan.plan_hash,
            attributes={
                "execution_status": result.status,
                "verified": result.verified,
                "rollback_ref": result.rollback_ref,
            },
            consequential=True,
        )
        return ActionOutcome(
            status=result.status,
            reason=result.policy.reason,
            execution_ref=result.execution_ref,
            verified=result.verified,
            rollback_ref=result.rollback_ref,
            error=result.error,
            from_status=WorkflowStatus.VERIFYING.value,
            workflow_version=verifying.workflow_version,
        )

    @activity.defn(name=RECORD_OUTCOME_ACTIVITY)
    def record_outcome(
        self,
        request: RemediationRequest,
        plan: RemediationPlanResult | None,
        outcome: ActionOutcome,
        approver: str,
        occurred_at: str,
    ) -> RemediationOutcome:
        require_remediation_workflows("record_outcome", self.environ)
        status = terminal_status_for_action(outcome)
        result = self._advance(
            request,
            step="outcome",
            action="finish-remediation",
            from_status=WorkflowStatus(outcome.from_status),
            expected_version=outcome.workflow_version,
            to_status=_TERMINAL_WORKFLOW_STATUS[status],
            occurred_at=_require_step_time(occurred_at),
            plan_hash=plan.plan_hash if plan else None,
            attributes={
                "status": status,
                "reason": outcome.reason,
                "approver": approver,
                "execution_ref": outcome.execution_ref,
                "rollback_ref": outcome.rollback_ref,
                "verified": outcome.verified,
                "error": outcome.error,
            },
            consequential=True,
        )
        return RemediationOutcome(
            workflow_id=request.workflow_id,
            status=status,
            reason=outcome.reason,
            plan_hash=plan.plan_hash if plan else None,
            approver=approver,
            execution_ref=outcome.execution_ref,
            rollback_ref=outcome.rollback_ref,
            audit_event_hash=result.audit_event_hash,
            mutation_attempted=outcome.execution_ref is not None,
        )

    def _action_request(
        self, request: RemediationRequest, plan: RemediationPlanResult
    ) -> ActionRequest:
        return ActionRequest(
            service=request.service,
            environment=request.environment,
            runbook_id=str(plan.runbook_id),
            blast_radius=request.blast_radius,
        )


def build_remediation_activities(
    environ: Mapping[str, str] | None = None,
    *,
    bridge: ControlPlaneActivityBridge,
) -> RemediationActivities:
    """Construct the remediation activities from environment configuration.

    Fails closed with every missing variable named. There is no default
    endpoint, secret, namespace, or policy; and the only supported evidence
    source is an explicit reviewed fixture, because no production evidence
    provider has been wired to this worker yet.
    """
    source = os.environ if environ is None else environ
    required = (
        "EIP_REMEDIATION_APPROVAL_SECRET",
        "EIP_OPA_ENDPOINT",
        "EIP_REMEDIATION_SOURCE_NAMESPACE",
        "EIP_REMEDIATION_POLICY_PATH",
        "EIP_REMEDIATION_EVIDENCE_PROVIDER",
    )
    missing = [name for name in required if not str(source.get(name, "")).strip()]
    if missing:
        raise RemediationConfigurationError(
            "remediation activities are incomplete; required: " + ", ".join(missing)
        )
    provider_spec = str(source["EIP_REMEDIATION_EVIDENCE_PROVIDER"]).strip()
    if not provider_spec.startswith("fixture:"):
        raise RemediationConfigurationError(
            "EIP_REMEDIATION_EVIDENCE_PROVIDER must be 'fixture:<path>'; no production "
            "evidence provider is wired to the remediation worker"
        )
    namespace = str(source["EIP_REMEDIATION_SOURCE_NAMESPACE"]).strip()
    return RemediationActivities(
        bridge=bridge,
        catalog=default_catalog(),
        autonomy_policies=load_service_autonomy(source["EIP_REMEDIATION_POLICY_PATH"]),
        adapter=KubernetesActionAdapter(namespace=namespace),
        evidence_provider=JsonFixtureEvidenceProvider(provider_spec[len("fixture:") :]),
        approval_secret=str(source["EIP_REMEDIATION_APPROVAL_SECRET"]),
        evaluator=OpaPolicyClient(str(source["EIP_OPA_ENDPOINT"])),
        twin=KubernetesDigitalTwin(),
        twin_source_namespace=namespace,
        environ=source,
    )
