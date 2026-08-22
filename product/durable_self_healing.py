from __future__ import annotations

from dataclasses import dataclass

from control_plane.remediation import RemediationWorkflowPlan, RemediationWorkflows
from intelligence.incidents import IncidentAnalysis
from orchestration.approvals import Approval
from orchestration.jobs import Job, SqliteJobQueue
from remediation.catalog import RunbookCatalog
from remediation.executor import ActionAdapter, ExecutionResult, execute_control_loop
from remediation.planner import RemediationPlan, plan_from_incident
from remediation.policy import ActionRequest, ServiceAutonomy
from remediation.simulation import simulate
from state.models import WorkflowRecord


@dataclass(frozen=True)
class PreparedRemediation:
    workflow: WorkflowRecord
    plan: RemediationPlan
    blast_radius: int


class DurableSelfHealingCoordinator:
    JOB_KIND = "certified-remediation"

    def __init__(
        self,
        *,
        workflows: RemediationWorkflows,
        queue: SqliteJobQueue,
        catalog: RunbookCatalog,
        policy: ServiceAutonomy,
        adapter: ActionAdapter,
        sandbox_adapter: ActionAdapter,
        approval_secret: str,
    ) -> None:
        self.workflows = workflows
        self.queue = queue
        self.catalog = catalog
        self.policy = policy
        self.adapter = adapter
        self.sandbox_adapter = sandbox_adapter
        self.approval_secret = approval_secret

    def prepare(self, analysis: IncidentAnalysis, *, incident_id: str, blast_radius: int) -> PreparedRemediation | None:
        plan = plan_from_incident(analysis)
        if plan is None:
            return None
        workflow_plan = RemediationWorkflowPlan(
            workflow_id=f"remediation:{incident_id}",
            service=self.policy.service,
            environment=self.policy.environment,
            runbook_id=plan.runbook_id,
            blast_radius=blast_radius,
            evidence_ids=plan.evidence_ids,
            confidence=plan.confidence,
        )
        workflow = self.workflows.prepare(workflow_plan)
        return PreparedRemediation(workflow, plan, blast_radius)

    def approve_and_enqueue(
        self,
        prepared: PreparedRemediation,
        *,
        approval: Approval,
        error_budget_remaining: float = 1.0,
        now: int | None = None,
    ) -> bool:
        self.workflows.approve(
            workflow_id=prepared.workflow.workflow_id,
            approval=approval,
            secret=self.approval_secret,
            now=now,
        )
        return self.queue.enqueue(
            job_id=f"{prepared.workflow.workflow_id}:{prepared.workflow.plan_hash}",
            workflow_id=prepared.workflow.workflow_id,
            kind=self.JOB_KIND,
            payload={
                "service": self.policy.service,
                "environment": self.policy.environment,
                "runbook_id": prepared.plan.runbook_id,
                "blast_radius": prepared.blast_radius,
                "approval_verified": True,
                "error_budget_remaining": error_budget_remaining,
            },
        )

    def handle_job(self, job: Job) -> ExecutionResult:
        if job.kind != self.JOB_KIND:
            raise ValueError("unexpected remediation job kind")
        if job.payload.get("approval_verified") is not True:
            raise PermissionError("durable remediation job was not created from a verified approval")
        request = ActionRequest(
            service=str(job.payload["service"]),
            environment=str(job.payload["environment"]),
            runbook_id=str(job.payload["runbook_id"]),
            blast_radius=int(job.payload["blast_radius"]),
            approval_token=f"verified:{job.workflow_id}",
            error_budget_remaining=float(job.payload.get("error_budget_remaining", 1.0)),
        )
        simulation = simulate(
            catalog=self.catalog,
            policy=self.policy,
            request=request,
            sandbox_adapter=self.sandbox_adapter,
        )
        if not simulation.safe_to_promote:
            raise RuntimeError("sandbox verification failed; production promotion blocked")
        result = execute_control_loop(
            catalog=self.catalog,
            policy=self.policy,
            request=request,
            adapter=self.adapter,
        )
        self.workflows.finish(
            workflow_id=job.workflow_id,
            status=result.status,
            execution_ref=result.execution_ref,
            rollback_ref=result.rollback_ref,
        )
        return result
