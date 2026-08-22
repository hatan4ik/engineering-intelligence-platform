from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from control_plane.workflows import ControlPlaneWorkflows
from intelligence.incidents import EvidenceEvent, IncidentAnalysis, analyze_incident
from topology.store import SqliteTopologyStore


class IncidentEvidenceProvider(Protocol):
    def collect(self, *, incident_id: str, service: str, environment: str) -> list[EvidenceEvent]: ...


class IncidentPublisher(Protocol):
    def publish(self, *, incident_id: str, service: str, analysis: IncidentAnalysis, impacted_services: tuple[str, ...]) -> None: ...


@dataclass(frozen=True)
class IncidentResult:
    workflow_id: str
    analysis: IncidentAnalysis
    impacted_services: tuple[str, ...]


class IncidentIntelligenceService:
    def __init__(
        self,
        *,
        evidence: IncidentEvidenceProvider,
        topology: SqliteTopologyStore,
        workflows: ControlPlaneWorkflows,
        publisher: IncidentPublisher,
    ) -> None:
        self.evidence = evidence
        self.topology = topology
        self.workflows = workflows
        self.publisher = publisher

    def investigate(self, *, incident_id: str, service: str, environment: str) -> IncidentResult:
        events = self.evidence.collect(incident_id=incident_id, service=service, environment=environment)
        analysis = analyze_incident(events, service=service)
        radius = self.topology.blast_radius({service})
        impacted = radius.impacted_services or (service,)
        workflow = self.workflows.start_incident(
            service_id=service,
            environment=environment,
            incident_id=incident_id,
            analysis=analysis,
        )
        self.publisher.publish(
            incident_id=incident_id,
            service=service,
            analysis=analysis,
            impacted_services=impacted,
        )
        return IncidentResult(workflow.workflow_id, analysis, impacted)
