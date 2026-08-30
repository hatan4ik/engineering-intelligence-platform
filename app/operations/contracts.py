"""Typed boundary records for operational-intelligence inputs and responses."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel


@dataclass(frozen=True)
class IncidentTrigger:
    """The explicit scope supplied by an Azure Monitor common-alert-schema event."""

    incident_id: str
    service: str
    environment: str
    fired: bool


class HypothesisResponse(BaseModel):
    title: str
    confidence: float
    facts: list[str]
    inferences: list[str]
    evidence_ids: list[str]


class TimelineEventResponse(BaseModel):
    id: str
    kind: str
    service: str
    timestamp: str
    summary: str
    source: str
    severity: int


class IncidentAnalysisResponse(BaseModel):
    hypotheses: list[HypothesisResponse]
    timeline: list[TimelineEventResponse]


class DeploymentAnalysisResponse(BaseModel):
    deployment_id: str
    service: str
    facts: list[str]
    hypotheses: list[HypothesisResponse]
    evidence_ids: list[str]


class ProposalResponse(BaseModel):
    kind: Literal["runbook", "corrective-pr", "ticket"]
    title: str
    exact_action: str
    rollback_path: str
    evidence_refs: list[str]
    requires_human: Literal[True]


class InvestigationResponse(BaseModel):
    """Fields every L2 proposal response must carry by construction."""

    status: Literal["investigated"] = "investigated"
    autonomy_level: Literal["L2-propose"] = "L2-propose"
    executed: Literal[False] = False
    correlation_id: str
    workflow_id: str
    service: str
    environment: str
    proposals: list[ProposalResponse]


class DeploymentInvestigationResponse(InvestigationResponse):
    analysis: DeploymentAnalysisResponse


class IncidentInvestigationResponse(InvestigationResponse):
    incident_id: str
    impacted_services: list[str]
    analysis: IncidentAnalysisResponse


class IgnoredIncidentResponse(BaseModel):
    status: Literal["ignored"] = "ignored"
    reason: Literal["monitorCondition is not Fired"] = "monitorCondition is not Fired"
