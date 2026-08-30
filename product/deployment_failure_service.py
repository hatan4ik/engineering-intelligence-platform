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
    # ``evidence`` is the timeline the analysis was derived from. A publisher that
    # renders L2 proposals needs it: DeploymentFailureAnalysis keeps derived facts
    # only, so the deployment events (and their commit attributes) are not in it.
    def publish(
        self,
        *,
        event: DeploymentFailureEvent,
        analysis: DeploymentFailureAnalysis,
        evidence: tuple[EvidenceEvent, ...],
    ) -> None: ...


@dataclass(frozen=True)
class DeploymentFailureResult:
    workflow_id: str
    analysis: DeploymentFailureAnalysis
    #: Correlation id of the control-plane workflow, echoed by the trigger routes.
    correlation_id: str = ""
    #: The evidence the analysis was derived from. ``DeploymentFailureAnalysis``
    #: keeps only derived facts, but L2 proposals need the deployment events to
    #: name an exact commit range.
    evidence: tuple[EvidenceEvent, ...] = ()


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

    async def investigate(
        self, event: DeploymentFailureEvent, *, correlation_id: str | None = None
    ) -> DeploymentFailureResult:
        events = self.evidence.evidence_for(event)
        analysis = investigate_deployment_failure(
            events,
            deployment_id=event.deployment_id,
            service=event.service,
        )
        workflow = await self.workflows.start_deployment_failure(
            environment=event.environment,
            analysis=analysis,
            correlation_id=correlation_id,
        )
        self.publisher.publish(event=event, analysis=analysis, evidence=tuple(events))
        return DeploymentFailureResult(
            workflow_id=workflow.workflow_id,
            analysis=analysis,
            correlation_id=workflow.correlation_id,
            evidence=tuple(events),
        )
