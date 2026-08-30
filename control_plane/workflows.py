from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, replace

from intelligence.deployment_failures import DeploymentFailureAnalysis
from intelligence.drift import DriftFinding
from intelligence.incidents import IncidentAnalysis
from intelligence.pr_guardian import PRPolicyDecision, policy_for
from intelligence.risk import RiskAssessment
from orchestration.approvals import Approval, verify_approval
from control_plane.correlation import resolve_correlation_id
from state.audit import AuditLog
from state.models import AuditEvent, WorkflowRecord, WorkflowStatus
from state.store import StateStore


def _hash(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return "sha256:" + hashlib.sha256(payload.encode()).hexdigest()


class ControlPlaneWorkflows:
    """Records product workflows in authoritative state and the audit log.

    The methods are coroutines so callers already integrate with an async
    control plane; durable orchestration of *consequential* work is the gated
    ``eip.remediation.v1`` workflow (ADR-001), not something started here.
    """

    def __init__(self, store: StateStore, audit: AuditLog) -> None:
        self.store = store
        self.audit = audit

    async def start_pr_review(
        self,
        *,
        service_id: str,
        repository: str,
        pr_number: int,
        assessment: RiskAssessment,
        simulated_policy: PRPolicyDecision | None = None,
        actor: str = "agent:pr-guardian",
        correlation_id: str | None = None,
    ) -> tuple[WorkflowRecord, PRPolicyDecision]:
        workflow_id = f"pr:{repository}:{pr_number}"
        resolved_correlation_id = resolve_correlation_id(correlation_id)
        maximum_policy = policy_for(assessment)
        policy = simulated_policy or maximum_policy
        if any(
            getattr(policy, field) and not getattr(maximum_policy, field)
            for field in ("require_extended_tests", "require_additional_approval", "block_merge")
        ):
            raise ValueError("simulated PR policy may only reduce the deterministic policy")
        plan_hash = _hash({"assessment": asdict(assessment), "policy": asdict(policy)})
        workflow = self.store.put_workflow(
            WorkflowRecord(
                workflow_id=workflow_id,
                service_id=service_id,
                environment="sdlc",
                kind="pr-review",
                status=WorkflowStatus.PLANNED,
                correlation_id=resolved_correlation_id,
                plan_hash=plan_hash,
            )
        )
        self.audit.append(
            AuditEvent(
                event_id=f"{workflow_id}:risk:{workflow.version}",
                correlation_id=resolved_correlation_id,
                actor=actor,
                action="assess-change-risk",
                resource=workflow_id,
                payload={
                    "score": assessment.score,
                    "band": assessment.band,
                    "blast_radius": list(assessment.blast_radius),
                    "policy": asdict(policy),
                    "plan_hash": plan_hash,
                },
            )
        )
        return workflow, policy

    async def start_incident(
        self,
        *,
        service_id: str,
        environment: str,
        incident_id: str,
        analysis: IncidentAnalysis,
        actor: str = "agent:incident-investigator",
        correlation_id: str | None = None,
    ) -> WorkflowRecord:
        workflow_id = f"incident:{incident_id}"
        resolved_correlation_id = resolve_correlation_id(correlation_id)
        evidence_ids = sorted(
            {
                e.id
                for hypothesis in analysis.hypotheses
                for e in analysis.timeline
                if e.id in hypothesis.evidence_ids
            }
        )
        plan_hash = _hash(
            {
                "hypotheses": [asdict(h) for h in analysis.hypotheses],
                "evidence_ids": evidence_ids,
            }
        )
        workflow = self.store.put_workflow(
            WorkflowRecord(
                workflow_id=workflow_id,
                service_id=service_id,
                environment=environment,
                kind="incident-investigation",
                status=WorkflowStatus.PLANNED,
                correlation_id=resolved_correlation_id,
                plan_hash=plan_hash,
            )
        )
        self.audit.append(
            AuditEvent(
                event_id=f"{workflow_id}:analysis:{workflow.version}",
                correlation_id=resolved_correlation_id,
                actor=actor,
                action="analyze-incident",
                resource=workflow_id,
                payload={
                    "hypothesis_count": len(analysis.hypotheses),
                    "evidence_ids": evidence_ids,
                    "plan_hash": plan_hash,
                },
            )
        )
        return workflow

    async def start_deployment_failure(
        self,
        *,
        environment: str,
        analysis: DeploymentFailureAnalysis,
        actor: str = "agent:deployment-failure-investigator",
        correlation_id: str | None = None,
    ) -> WorkflowRecord:
        workflow_id = f"deployment-failure:{analysis.deployment_id}"
        resolved_correlation_id = resolve_correlation_id(correlation_id)
        plan_hash = _hash(asdict(analysis))
        workflow = self.store.put_workflow(
            WorkflowRecord(
                workflow_id=workflow_id,
                service_id=analysis.service,
                environment=environment,
                kind="deployment-failure-investigation",
                status=WorkflowStatus.PLANNED,
                correlation_id=resolved_correlation_id,
                plan_hash=plan_hash,
            )
        )
        self.audit.append(
            AuditEvent(
                event_id=f"{workflow_id}:analysis:{workflow.version}",
                correlation_id=resolved_correlation_id,
                actor=actor,
                action="investigate-deployment-failure",
                resource=workflow_id,
                payload={
                    "deployment_id": analysis.deployment_id,
                    "hypothesis_count": len(analysis.hypotheses),
                    "evidence_ids": list(analysis.evidence_ids),
                    "plan_hash": plan_hash,
                },
            )
        )
        return workflow

    async def start_drift_review(
        self,
        *,
        resource_id: str,
        service_id: str,
        environment: str,
        findings: tuple[DriftFinding, ...],
        actor: str = "agent:drift-detector",
        correlation_id: str | None = None,
    ) -> WorkflowRecord:
        workflow_id = f"drift:{environment}:{resource_id}"
        resolved_correlation_id = resolve_correlation_id(correlation_id)
        plan_hash = _hash([asdict(f) for f in findings])
        status = WorkflowStatus.PLANNED if findings else WorkflowStatus.SUCCEEDED
        workflow = self.store.put_workflow(
            WorkflowRecord(
                workflow_id=workflow_id,
                service_id=service_id,
                environment=environment,
                kind="drift-review",
                status=status,
                correlation_id=resolved_correlation_id,
                plan_hash=plan_hash,
            )
        )
        self.audit.append(
            AuditEvent(
                event_id=f"{workflow_id}:scan:{workflow.version}",
                correlation_id=resolved_correlation_id,
                actor=actor,
                action="detect-drift",
                resource=workflow_id,
                payload={
                    "finding_count": len(findings),
                    "max_severity": max((f.severity for f in findings), default=0),
                    "fields": [f.field for f in findings],
                    "plan_hash": plan_hash,
                },
            )
        )
        return workflow

    def approve_plan(
        self,
        *,
        workflow_id: str,
        approval: Approval,
        secret: str,
        now: int | None = None,
    ) -> WorkflowRecord:
        workflow = self.store.get_workflow(workflow_id)
        if workflow is None or workflow.plan_hash is None:
            raise ValueError("workflow or plan not found")
        if not verify_approval(
            approval,
            expected_workflow_id=workflow.workflow_id,
            expected_plan_hash=workflow.plan_hash,
            secret=secret,
            now=now,
        ):
            raise PermissionError("approval is invalid, stale, expired, or for a different plan")
        updated = self.store.put_workflow(
            replace(workflow, status=WorkflowStatus.EXECUTING),
            expected_version=workflow.version,
        )
        self.audit.append(
            AuditEvent(
                event_id=f"{workflow_id}:approval:{updated.version}",
                correlation_id=workflow.correlation_id,
                actor=f"human:{approval.approver}",
                action="approve-plan",
                resource=workflow_id,
                payload={"plan_hash": workflow.plan_hash},
            )
        )
        return updated
