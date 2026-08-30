"""The initial, non-consequential Temporal workflow contract.

This worker proves durable Temporal scheduling and mTLS client configuration
without mutating Cosmos, audit evidence, or infrastructure.  Consequential
control-plane activities remain unavailable until their authoritative-state and
immutable-audit adapters are implemented and independently exercised.

This module deliberately defines only the evidence workflow. The gated
remediation workflow lives in ``orchestration.remediation_workflow`` under the
name ``eip.remediation.v1``; no other module may declare a workflow with that
name (``tests/test_temporal_workflow_names.py`` enforces uniqueness), because a
second definition that returned success without running the control loop would
be indistinguishable from the real one at registration time.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from temporalio import workflow

from telemetry.trace_context import TraceContext


_REQUEST_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_CORRELATION_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


@dataclass(frozen=True)
class ControlPlaneEvidenceRequest:
    """A bounded proof request that has no external side effects."""

    request_id: str
    correlation_id: str
    trace_context: TraceContext = field(default_factory=TraceContext)

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
    trace_context: TraceContext = field(default_factory=TraceContext)
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
            trace_context=request.trace_context,
        )
