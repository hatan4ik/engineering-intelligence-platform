"""Typed presentation of L1 analysis and L2 human-executed proposals."""

from __future__ import annotations

from collections.abc import Sequence

from integrations.azure_devops.deployment_failure import DeploymentFailureEvent
from intelligence.deployment_failures import DeploymentFailureAnalysis
from intelligence.incidents import EvidenceEvent, IncidentAnalysis
from product.deployment_failure_service import DeploymentFailureResult
from product.incident_service import IncidentResult
from product.l2_proposals import L2Proposal, build_proposals

from .contracts import (
    DeploymentAnalysisResponse,
    DeploymentInvestigationResponse,
    HypothesisResponse,
    IncidentAnalysisResponse,
    IncidentInvestigationResponse,
    IncidentTrigger,
    ProposalResponse,
    TimelineEventResponse,
)


def deployment_report(
    event: DeploymentFailureEvent,
    result: DeploymentFailureResult,
) -> DeploymentInvestigationResponse:
    """Construct the non-executing response for a deployment investigation."""

    return DeploymentInvestigationResponse(
        correlation_id=result.correlation_id,
        workflow_id=result.workflow_id,
        service=event.service,
        environment=event.environment,
        analysis=DeploymentAnalysisResponse(
            deployment_id=result.analysis.deployment_id,
            service=result.analysis.service,
            facts=list(result.analysis.facts),
            hypotheses=_hypotheses(result.analysis),
            evidence_ids=list(result.analysis.evidence_ids),
        ),
        proposals=_proposals(
            build_proposals(
                result.analysis,
                service=event.service,
                environment=event.environment,
                evidence=result.evidence,
            )
        ),
    )


def incident_report(
    trigger: IncidentTrigger,
    result: IncidentResult,
) -> IncidentInvestigationResponse:
    """Construct the non-executing response for an incident correlation."""

    return IncidentInvestigationResponse(
        correlation_id=result.correlation_id,
        workflow_id=result.workflow_id,
        incident_id=trigger.incident_id,
        service=trigger.service,
        environment=trigger.environment,
        impacted_services=list(result.impacted_services),
        analysis=IncidentAnalysisResponse(
            hypotheses=_hypotheses(result.analysis),
            timeline=_timeline(result.analysis.timeline),
        ),
        proposals=_proposals(
            build_proposals(
                result.analysis,
                service=trigger.service,
                environment=trigger.environment,
            )
        ),
    )


def _hypotheses(
    analysis: IncidentAnalysis | DeploymentFailureAnalysis,
) -> list[HypothesisResponse]:
    return [
        HypothesisResponse(
            title=hypothesis.title,
            confidence=round(hypothesis.confidence, 4),
            facts=list(hypothesis.facts),
            inferences=list(hypothesis.inferences),
            evidence_ids=list(hypothesis.evidence_ids),
        )
        for hypothesis in analysis.hypotheses
    ]


def _timeline(events: Sequence[EvidenceEvent]) -> list[TimelineEventResponse]:
    return [
        TimelineEventResponse(
            id=event.id,
            kind=event.kind.value,
            service=event.service,
            timestamp=event.timestamp.isoformat(),
            summary=event.summary,
            source=event.source,
            severity=event.severity,
        )
        for event in events
    ]


def _proposals(proposals: Sequence[L2Proposal]) -> list[ProposalResponse]:
    return [
        ProposalResponse(
            kind=proposal.kind,
            title=proposal.title,
            exact_action=proposal.exact_action,
            rollback_path=proposal.rollback_path,
            evidence_refs=list(proposal.evidence_refs),
            requires_human=proposal.requires_human,
        )
        for proposal in proposals
    ]
