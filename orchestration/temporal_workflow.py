"""The initial, non-consequential Temporal workflow contract.

This worker proves durable Temporal scheduling and mTLS client configuration
without mutating Cosmos, audit evidence, or infrastructure.  Consequential
control-plane activities remain unavailable until their authoritative-state and
immutable-audit adapters are implemented and independently exercised.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from temporalio import workflow


_REQUEST_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_CORRELATION_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


@dataclass(frozen=True)
class ControlPlaneEvidenceRequest:
    """A bounded proof request that has no external side effects."""

    request_id: str
    correlation_id: str

    def validate(self) -> None:
        if not _REQUEST_ID.fullmatch(self.request_id):
            raise ValueError("request_id must be a bounded opaque identifier")
        if not _CORRELATION_ID.fullmatch(self.correlation_id):
            raise ValueError("correlation_id must be a bounded opaque identifier")

    @property
    def workflow_id(self) -> str:
        self.validate()
        return f"eip-control-plane-evidence:{self.request_id}"


@dataclass(frozen=True)
class ControlPlaneEvidenceResult:
    workflow_id: str
    request_id: str
    correlation_id: str
    capability: str = "temporal-control-plane-evidence"
    mutation_performed: bool = False


@workflow.defn(name="eip.control-plane-evidence.v1")
class ControlPlaneEvidenceWorkflow:
    """A deterministic Temporal workflow used only for integration evidence."""

    @workflow.run
    async def run(self, request: ControlPlaneEvidenceRequest) -> ControlPlaneEvidenceResult:
        request.validate()
        return ControlPlaneEvidenceResult(
            workflow_id=workflow.info().workflow_id,
            request_id=request.request_id,
            correlation_id=request.correlation_id,
        )

from datetime import timedelta
from intelligence.risk import RiskAssessment
from intelligence.pr_guardian import PRPolicyDecision

@dataclass(frozen=True)
class PRGuardianRequest:
    service_id: str
    repository: str
    pr_number: int
    assessment: RiskAssessment
    correlation_id: str

@dataclass(frozen=True)
class RemediationRequest:
    incident_id: str
    service_id: str
    runbook_id: str
    correlation_id: str

@workflow.defn(name="eip.pr-review.v1")
class PRGuardianWorkflow:
    """Orchestrates the PR Guardian review cycle via Temporal."""

    @workflow.run
    async def run(self, request: PRGuardianRequest) -> dict[str, str]:
        # In the future, this will schedule activities like 'RecordAssessmentActivity'
        # and 'AuditActivity'.
        # For now, it represents the durable workflow shell.
        return {
            "status": "completed",
            "correlation_id": request.correlation_id,
            "workflow_id": workflow.info().workflow_id
        }

@workflow.defn(name="eip.remediation.v1")
class RemediationWorkflow:
    """Orchestrates L3/L4 self-healing via Temporal."""

    @workflow.run
    async def run(self, request: RemediationRequest) -> dict[str, str]:
        # Would wait for approval signal here if L3
        return {
            "status": "completed",
            "correlation_id": request.correlation_id,
            "workflow_id": workflow.info().workflow_id
        }
