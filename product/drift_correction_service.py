from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from control_plane.workflows import ControlPlaneWorkflows
from intelligence.drift import ResourceSnapshot, detect_drift
from intelligence.drift_correction import DriftCorrectionPlan, build_correction_plan


class DesiredStateWithSourceProvider(Protocol):
    def desired(self, *, service: str, environment: str) -> list[ResourceSnapshot]: ...

    def source_location(self, snapshot: ResourceSnapshot) -> tuple[str | None, str | None]: ...


class CorrectionPlanPublisher(Protocol):
    def publish_plan(self, *, plan: DriftCorrectionPlan, workflow_id: str) -> None: ...


@dataclass(frozen=True)
class DriftCorrectionResult:
    workflow_ids: tuple[str, ...]
    plans: tuple[DriftCorrectionPlan, ...]


class DriftCorrectionService:
    """Turns observed drift into reviewable desired-state work, never direct mutation."""

    def __init__(
        self,
        *,
        provider: DesiredStateWithSourceProvider,
        workflows: ControlPlaneWorkflows,
        publisher: CorrectionPlanPublisher,
    ) -> None:
        self.provider = provider
        self.workflows = workflows
        self.publisher = publisher

    def run(self, *, service: str, environment: str) -> DriftCorrectionResult:
        workflow_ids: list[str] = []
        plans: list[DriftCorrectionPlan] = []
        for snapshot in self.provider.desired(service=service, environment=environment):
            findings = detect_drift(snapshot)
            if not findings:
                continue
            source_path, source_revision = self.provider.source_location(snapshot)
            plan = build_correction_plan(
                findings,
                source_path=source_path,
                source_revision=source_revision,
            )
            if plan is None:
                continue
            workflow = self.workflows.start_drift_review(
                resource_id=snapshot.resource_id,
                service_id=service,
                environment=environment,
                findings=findings,
            )
            self.publisher.publish_plan(plan=plan, workflow_id=workflow.workflow_id)
            workflow_ids.append(workflow.workflow_id)
            plans.append(plan)
        return DriftCorrectionResult(tuple(workflow_ids), tuple(plans))
