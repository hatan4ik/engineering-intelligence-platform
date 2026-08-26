import re

filepath = 'control_plane/workflows.py'
with open(filepath, 'r') as f:
    content = f.read()

# 1. Add imports
import_statement = """from state.store import StateStore

try:
    from temporalio.client import Client
except ImportError:
    Client = None
    
from orchestration.temporal_workflow import PRGuardianRequest
"""
content = content.replace("from state.store import StateStore", import_statement)

# 2. Update __init__
old_init = """    def __init__(self, store: StateStore, audit: AuditLog) -> None:
        self.store = store
        self.audit = audit"""
new_init = """    def __init__(self, store: StateStore, audit: AuditLog, temporal_client=None) -> None:
        self.store = store
        self.audit = audit
        self.temporal_client = temporal_client"""
content = content.replace(old_init, new_init)

# 3. Update start_pr_review
old_start = """    def start_pr_review(
        self,
        *,
        service_id: str,
        repository: str,
        pr_number: int,
        assessment: RiskAssessment,
        actor: str = "agent:pr-guardian",
    ) -> tuple[WorkflowRecord, PRPolicyDecision]:"""
new_start = """    async def start_pr_review(
        self,
        *,
        service_id: str,
        repository: str,
        pr_number: int,
        assessment: RiskAssessment,
        actor: str = "agent:pr-guardian",
    ) -> tuple[WorkflowRecord, PRPolicyDecision]:"""
content = content.replace(old_start, new_start)

# 4. Insert Temporal logic at the end of start_pr_review
old_return = """        return workflow, policy"""
new_return = """        
        if self.temporal_client:
            await self.temporal_client.start_workflow(
                "eip.pr-review.v1",
                PRGuardianRequest(
                    service_id=service_id,
                    repository=repository,
                    pr_number=pr_number,
                    assessment=assessment,
                    correlation_id=correlation_id
                ),
                id=workflow_id,
                task_queue="eip-control-plane"
            )
            
        return workflow, policy"""
content = content.replace(old_return, new_return)

with open(filepath, 'w') as f:
    f.write(content)
