"""Telemetry stage for PR Guardian review outcomes."""

from __future__ import annotations

from intelligence.risk import RiskAssessment
from integrations.github.pr_guardian import PullRequestEvent
from telemetry.events import OperationEvent, TelemetrySink

from .company_brain import PRGuardianCompanyContext
from .contracts import PRFinding


class PRGuardianTelemetryRecorder:
    """Emit the stable, non-secret review event after a use case completes."""

    def __init__(self, sink: TelemetrySink) -> None:
        self._sink = sink

    def record(
        self,
        *,
        event: PullRequestEvent,
        assessment: RiskAssessment,
        finding: PRFinding,
        primary_service: str,
        company_context: PRGuardianCompanyContext | None,
        conclusion: str,
        latency_ms: float,
    ) -> None:
        self._sink.emit(
            OperationEvent(
                correlation_id=finding.correlation_id,
                operation="pr-guardian-review",
                component="product.pr_guardian",
                outcome=conclusion,
                latency_ms=latency_ms,
                repo=event.repository,
                service=primary_service,
                agent="pr-guardian",
                attributes={
                    "pr": str(event.number),
                    "head_sha": event.head_sha,
                    "score": str(assessment.score),
                    "band": assessment.band,
                    "company_brain_context": (
                        "qualified"
                        if company_context is not None and company_context.qualified
                        else "unqualified"
                    ),
                    "context_version": finding.context_version,
                },
            )
        )
