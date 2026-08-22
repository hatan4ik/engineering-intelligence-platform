from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, replace

from orchestration.approvals import Approval, verify_approval
from state.audit import SqliteAuditLog
from state.models import AuditEvent, WorkflowRecord, WorkflowStatus
from state.store import StateStore


def _hash(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return "sha256:" + hashlib.sha256(payload.encode()).hexdigest()


@dataclass(frozen=True)
class RemediationWorkflowPlan:
    workflow_id: str
    service: str
    environment: str
    runbook_id: str
    blast_radius: int
    evidence_ids: tuple[str, ...]
    confidence: float

    def payload(self) -> dict[str, object]:
        return {
            "service": self.service,
            "environment": self.environment,
            "runbook_id": self.runbook_id,
            "blast_radius": self.blast_radius,
            "evidence_ids": list(self.evidence_ids),
            "confidence": self.confidence,
        }


class RemediationWorkflows:
    def __init__(self, store: StateStore, audit: SqliteAuditLog) -> None:
        self.store = store
        self.audit = audit

    def prepare(self, plan: RemediationWorkflowPlan) -> WorkflowRecord:
        plan_hash = _hash(plan.payload())
        workflow = self.store.put_workflow(WorkflowRecord(
            workflow_id=plan.workflow_id,
            service_id=plan.service,
            environment=plan.environment,
            kind="remediation",
            status=WorkflowStatus.WAITING_APPROVAL,
            correlation_id=str(uuid.uuid4()),
            plan_hash=plan_hash,
        ))
        self.audit.append(AuditEvent(
            event_id=f"{workflow.workflow_id}:planned:{workflow.version}",
            correlation_id=workflow.correlation_id,
            actor="agent:remediation-planner",
            action="prepare-remediation",
            resource=workflow.workflow_id,
            payload={**plan.payload(), "plan_hash": plan_hash},
        ))
        return workflow

    def approve(self, *, workflow_id: str, approval: Approval, secret: str, now: int | None = None) -> WorkflowRecord:
        workflow = self.store.get_workflow(workflow_id)
        if workflow is None or workflow.plan_hash is None:
            raise ValueError("remediation workflow or plan not found")
        if workflow.status is not WorkflowStatus.WAITING_APPROVAL:
            raise ValueError("workflow is not waiting for approval")
        if not verify_approval(
            approval,
            expected_workflow_id=workflow.workflow_id,
            expected_plan_hash=workflow.plan_hash,
            secret=secret,
            now=now,
        ):
            raise PermissionError("approval is invalid, stale, expired, or bound to another plan")
        updated = self.store.put_workflow(
            replace(workflow, status=WorkflowStatus.EXECUTING),
            expected_version=workflow.version,
        )
        self.audit.append(AuditEvent(
            event_id=f"{workflow_id}:approved:{updated.version}",
            correlation_id=workflow.correlation_id,
            actor=f"human:{approval.approver}",
            action="approve-remediation",
            resource=workflow_id,
            payload={"plan_hash": workflow.plan_hash},
        ))
        return updated

    def finish(self, *, workflow_id: str, status: str, execution_ref: str | None, rollback_ref: str | None) -> WorkflowRecord:
        workflow = self.store.get_workflow(workflow_id)
        if workflow is None:
            raise ValueError("remediation workflow not found")
        target = {
            "succeeded": WorkflowStatus.SUCCEEDED,
            "rolled_back": WorkflowStatus.ROLLED_BACK,
            "escalate": WorkflowStatus.ESCALATED,
            "denied": WorkflowStatus.FAILED,
        }.get(status, WorkflowStatus.FAILED)
        updated = self.store.put_workflow(replace(workflow, status=target), expected_version=workflow.version)
        self.audit.append(AuditEvent(
            event_id=f"{workflow_id}:result:{updated.version}",
            correlation_id=workflow.correlation_id,
            actor="agent:remediation-executor",
            action="finish-remediation",
            resource=workflow_id,
            payload={"status": status, "execution_ref": execution_ref, "rollback_ref": rollback_ref},
        ))
        return updated
