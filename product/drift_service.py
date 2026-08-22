from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Protocol

from control_plane.workflows import ControlPlaneWorkflows
from intelligence.drift import DriftFinding, ResourceSnapshot, detect_drift


class DesiredStateProvider(Protocol):
    def desired(self, *, service: str, environment: str) -> list[ResourceSnapshot]: ...


class DriftPublisher(Protocol):
    def publish(self, *, service: str, environment: str, findings: tuple[DriftFinding, ...]) -> None: ...


@dataclass(frozen=True)
class DriftResult:
    workflow_id: str
    findings: tuple[DriftFinding, ...]


class DriftDetectorService:
    def __init__(self, *, provider: DesiredStateProvider, workflows: ControlPlaneWorkflows, publisher: DriftPublisher) -> None:
        self.provider = provider
        self.workflows = workflows
        self.publisher = publisher

    def run(self, *, service: str, environment: str) -> DriftResult:
        findings = tuple(
            finding
            for snapshot in self.provider.desired(service=service, environment=environment)
            for finding in detect_drift(snapshot)
        )
        workflow = self.workflows.start_generic_workflow(
            workflow_id=f"drift:{environment}:{service}",
            service_id=service,
            environment=environment,
            kind="drift-detection",
            plan_payload={"findings": [asdict(f) for f in findings]},
        )
        self.publisher.publish(service=service, environment=environment, findings=findings)
        return DriftResult(workflow.workflow_id, findings)
