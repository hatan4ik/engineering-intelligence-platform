from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from control_plane.workflows import ControlPlaneWorkflows
from integrations.azure_devops.deployment_failure import DeploymentFailureEvent
from intelligence.deployment_failures import DeploymentFailureAnalysis, investigate_deployment_failure
from intelligence.incidents import EvidenceEvent


class DeploymentEvidenceProvider(Protocol):
    def evidence_for(self, event: DeploymentFailureEvent) -> list[EvidenceEvent]: ...


class DeploymentOutputPublisher(Protocol):
    def publish(self, *, event: DeploymentFailureEvent, analysis: DeploymentFailureAnalysis) -> None: ...


@dataclass(frozen=True)
class DeploymentFailureResult:
    workflow_id: str
    analysis: DeploymentFailureAnalysis


class DeploymentFailureInvestigatorService:
    def __init__(
        self,
        *,
        evidence: DeploymentEvidenceProvider,
        workflows: ControlPlaneWorkflows,
        publisher: DeploymentOutputPublisher,
    ) -> None:
        self.evidence = evidence
        self.workflows = workflows
        self.publisher = publisher

    async def investigate(self, event: DeploymentFailureEvent) -> DeploymentFailureResult:
        events = self.evidence.evidence_for(event)
        analysis = investigate_deployment_failure(
            events,
            deployment_id=event.deployment_id,
            service=event.service,
        )
        workflow = await self.workflows.start_deployment_failure(
            environment=event.environment,
            analysis=analysis,
        )
        self.publisher.publish(event=event, analysis=analysis)
        return DeploymentFailureResult(workflow_id=workflow.workflow_id, analysis=analysis)
