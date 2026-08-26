import re

filepath = 'control_plane/workflows.py'
with open(filepath, 'r') as f:
    content = f.read()

# Imports
content = content.replace("from orchestration.temporal_workflow import PRGuardianRequest", 
    "from orchestration.temporal_workflow import PRGuardianRequest, IncidentRequest, DeploymentFailureRequest, DriftReviewRequest")

# start_incident
content = content.replace(
    "def start_incident(", 
    "async def start_incident("
)

content = content.replace(
    "return workflow\n\n    async def start_deployment_failure(", 
    "return workflow\n\n    def start_deployment_failure(" # Revert my previous mistake if it happened
)

content = content.replace(
"""        self.audit.append(
            AuditEvent(
                event_id=f"{workflow_id}:analysis:{workflow.version}",
                correlation_id=correlation_id,
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
        return workflow""",
"""        self.audit.append(
            AuditEvent(
                event_id=f"{workflow_id}:analysis:{workflow.version}",
                correlation_id=correlation_id,
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
        if self.temporal_client:
            await self.temporal_client.start_workflow(
                "eip.incident.v1",
                IncidentRequest(
                    service_id=service_id,
                    environment=environment,
                    incident_id=incident_id,
                    analysis=analysis,
                    correlation_id=correlation_id
                ),
                id=workflow_id,
                task_queue="eip-control-plane"
            )
        return workflow"""
)

# start_deployment_failure
content = content.replace(
    "def start_deployment_failure(", 
    "async def start_deployment_failure("
)

content = content.replace(
"""        self.audit.append(
            AuditEvent(
                event_id=f"{workflow_id}:analysis:{workflow.version}",
                correlation_id=correlation_id,
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
        return workflow""",
"""        self.audit.append(
            AuditEvent(
                event_id=f"{workflow_id}:analysis:{workflow.version}",
                correlation_id=correlation_id,
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
        if self.temporal_client:
            await self.temporal_client.start_workflow(
                "eip.deployment-failure.v1",
                DeploymentFailureRequest(
                    service_id=analysis.service,
                    environment=environment,
                    deployment_id=analysis.deployment_id,
                    analysis=analysis,
                    correlation_id=correlation_id
                ),
                id=workflow_id,
                task_queue="eip-control-plane"
            )
        return workflow"""
)

# start_drift_review
content = content.replace(
    "def start_drift_review(", 
    "async def start_drift_review("
)

content = content.replace(
"""        self.audit.append(
            AuditEvent(
                event_id=f"{workflow_id}:scan:{workflow.version}",
                correlation_id=correlation_id,
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
        return workflow""",
"""        self.audit.append(
            AuditEvent(
                event_id=f"{workflow_id}:scan:{workflow.version}",
                correlation_id=correlation_id,
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
        if self.temporal_client:
            await self.temporal_client.start_workflow(
                "eip.drift-review.v1",
                DriftReviewRequest(
                    resource_id=resource_id,
                    service_id=service_id,
                    environment=environment,
                    findings=findings,
                    correlation_id=correlation_id
                ),
                id=workflow_id,
                task_queue="eip-control-plane"
            )
        return workflow"""
)

with open(filepath, 'w') as f:
    f.write(content)
