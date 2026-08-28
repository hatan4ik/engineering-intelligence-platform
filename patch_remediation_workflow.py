import re

filepath = 'orchestration/temporal_workflow.py'
with open(filepath, 'r') as f:
    content = f.read()

old_remediation = """@workflow.defn(name="eip.remediation.v1")
class RemediationWorkflow:
    \"\"\"Orchestrates L3/L4 self-healing via Temporal.\"\"\"

    @workflow.run
    async def run(self, request: RemediationRequest) -> dict[str, str]:
        # Would wait for approval signal here if L3
        return {
            "status": "completed",
            "correlation_id": request.correlation_id,
            "workflow_id": workflow.info().workflow_id
        }"""

new_remediation = """from temporalio import activity

@dataclass(frozen=True)
class ExecuteRunbookResult:
    success: bool
    output: str

@workflow.defn(name="eip.remediation.v1")
class RemediationWorkflow:
    \"\"\"Orchestrates L3/L4 self-healing via Temporal.\"\"\"

    @workflow.run
    async def run(self, request: RemediationRequest) -> dict[str, str]:
        # Execute the runbook via a Temporal Activity (Digital Twin + OPA Check -> Apply)
        result = await workflow.execute_activity(
            "execute_remediation_runbook",
            request,
            start_to_close_timeout=timedelta(minutes=5),
        )
        
        return {
            "status": "completed" if result.success else "failed",
            "correlation_id": request.correlation_id,
            "workflow_id": workflow.info().workflow_id,
            "output": result.output
        }"""

content = content.replace(old_remediation, new_remediation)

with open(filepath, 'w') as f:
    f.write(content)
