from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from control_plane.workflows import ControlPlaneWorkflows
from intelligence.drift import DriftFinding, ResourceSnapshot, detect_drift


class DesiredStateProvider(Protocol):
    def desired(self, *, service: str, environment: str) -> list[ResourceSnapshot]: ...


class DriftPublisher(Protocol):
    def publish(self, *, service: str, environment: str, findings: tuple[DriftFinding, ...]) -> None: ...


@dataclass(frozen=True)
class DriftResult:
    workflow_ids: tuple[str, ...]
    findings: tuple[DriftFinding, ...]


class DriftDetectorService:
    def __init__(self, *, provider: DesiredStateProvider, workflows: ControlPlaneWorkflows, publisher: DriftPublisher) -> None:
        self.provider = provider
        self.workflows = workflows
        self.publisher = publisher

    async def run(self, *, service: str, environment: str) -> DriftResult:
        snapshots = self.provider.desired(service=service, environment=environment)
        all_findings: list[DriftFinding] = []
        workflow_ids: list[str] = []
        for snapshot in snapshots:
            findings = detect_drift(snapshot)
            all_findings.extend(findings)
            workflow = await self.workflows.start_drift_review(
                resource_id=snapshot.resource_id,
                service_id=service,
                environment=environment,
                findings=findings,
            )
            workflow_ids.append(workflow.workflow_id)
        result = tuple(all_findings)
        self.publisher.publish(service=service, environment=environment, findings=result)
        return DriftResult(tuple(workflow_ids), result)
