"""The PR Guardian application-service facade.

The public service owns the use-case ordering: prepare a review, record its
durable workflow, determine the repository-owned enforcement decision, and
then optionally present the result. The detailed read, finding, publishing,
and telemetry mechanisms live in focused PR Guardian components.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Mapping

from company_brain.artifact_outbox import ArtifactOutbox
from company_brain.model import BrainPrincipal
from control_plane.workflows import ControlPlaneWorkflows
from intelligence.graph import ServiceGraph
from intelligence.pr_guardian import PRPolicyDecision
from intelligence.risk import RiskAssessment
from integrations.github.pr_guardian import GitHubPRClient, PullRequestEvent
from product.pr_guardian.company_brain import PRGuardianCompanyContext
from product.pr_guardian.config import default_shadow_config
from product.pr_guardian.contracts import PRFinding, ProductMode, RepositoryConfig
from product.pr_guardian.enforcement import (
    EnforcementDecision,
    PublishConclusion,
    REASON_CONTEXT_UNQUALIFIED,
    enforcement_decision,
)
from product.pr_guardian.finding_factory import PRFindingFactory
from product.pr_guardian.publication import PRGuardianPublisher
from product.pr_guardian.review_pipeline import (
    HistoricalFailureProvider,
    PRReviewPreparer,
    QualifiedCompanyContextProvider,
)
from product.pr_guardian.store import PRGuardianFindingStore
from product.pr_guardian.telemetry import PRGuardianTelemetryRecorder
from telemetry.events import NullTelemetrySink, TelemetrySink


@dataclass(frozen=True)
class PRGuardianResult:
    assessment: RiskAssessment
    policy: PRPolicyDecision
    workflow_id: str
    correlation_id: str
    conclusion: PublishConclusion
    changed_services: tuple[str, ...]
    changed_files: tuple[str, ...]
    mode: ProductMode
    simulated_policy_would_block: bool
    repository_enforcement_would_block: bool
    enforcement: EnforcementDecision
    finding: PRFinding | None
    company_context: PRGuardianCompanyContext | None
    publication_artifact_id: str | None

    @property
    def would_block(self) -> bool:
        """Compatibility alias for the simulated policy result.

        New callers must use ``simulated_policy_would_block`` or
        ``repository_enforcement_would_block`` so shadow/advisory policy output
        cannot be confused with the repository-owned enforcement decision.
        """

        return self.simulated_policy_would_block


@dataclass(frozen=True)
class PRGuardianDependencies:
    """Immutable composition inputs captured by one PR Guardian service instance."""

    graph: ServiceGraph | None
    github: GitHubPRClient
    workflows: ControlPlaneWorkflows
    history: HistoricalFailureProvider | None
    telemetry: TelemetrySink
    config: RepositoryConfig | None
    environ: Mapping[str, str] | None
    company_context: QualifiedCompanyContextProvider | None
    principal: BrainPrincipal | None
    findings: PRGuardianFindingStore | None
    publication_outbox: ArtifactOutbox | None


class PRGuardianService:
    """Product use case for an evidence-backed GitHub PR risk check.

    GitHub is only an event/output adapter. Risk scoring remains deterministic,
    and the durable control plane records the exact assessment and policy plan.
    """

    __slots__ = (
        "_dependencies",
        "_mode",
        "_policy_version",
        "_preparer",
        "_finding_factory",
        "_publisher",
        "_telemetry_recorder",
    )

    def __init__(
        self,
        *,
        graph: ServiceGraph | None,
        github: GitHubPRClient,
        workflows: ControlPlaneWorkflows,
        history: HistoricalFailureProvider | None = None,
        telemetry: TelemetrySink | None = None,
        mode: ProductMode | str = ProductMode.SHADOW,
        config: RepositoryConfig | None = None,
        environ: Mapping[str, str] | None = None,
        company_context: QualifiedCompanyContextProvider | None = None,
        principal: BrainPrincipal | None = None,
        findings: PRGuardianFindingStore | None = None,
        publication_outbox: ArtifactOutbox | None = None,
        policy_version: str = "pr-policy-v1",
    ) -> None:
        if config is not None:
            resolved = config.mode
        elif mode is ProductMode.SHADOW or mode == ProductMode.SHADOW.value:
            # Preserve the legacy shadow-only construction value at the public
            # boundary while keeping every internal flow enum-typed.
            resolved = ProductMode.SHADOW
        else:
            raise ValueError(
                "a non-shadow PR Guardian mode must come from the repository configuration"
            )
        if graph is None and company_context is None:
            raise ValueError("PR Guardian requires a graph or qualified Company Brain context")
        if company_context is not None and principal is None:
            raise ValueError("qualified Company Brain context requires a principal")
        if not isinstance(policy_version, str) or not policy_version or "\n" in policy_version:
            raise ValueError("policy_version is invalid")

        self._dependencies = PRGuardianDependencies(
            graph=graph,
            github=github,
            workflows=workflows,
            history=history,
            telemetry=telemetry or NullTelemetrySink(),
            config=config,
            environ=environ,
            company_context=company_context,
            principal=principal,
            findings=findings,
            publication_outbox=publication_outbox,
        )
        self._mode = resolved
        self._policy_version = config.policy_version if config is not None else policy_version

        self._preparer = PRReviewPreparer(
            graph=self._dependencies.graph,
            github=self._dependencies.github,
            history=self._dependencies.history,
            company_context=self._dependencies.company_context,
            principal=self._dependencies.principal,
        )
        self._finding_factory = PRFindingFactory(policy_version=self._policy_version)
        self._publisher = (
            PRGuardianPublisher(self._dependencies.github, publication_outbox)
            if publication_outbox is not None
            else None
        )
        self._telemetry_recorder = PRGuardianTelemetryRecorder(self._dependencies.telemetry)

    @property
    def mode(self) -> ProductMode:
        """The repository-derived operating mode fixed at service construction."""

        return self._mode

    @property
    def policy_version(self) -> str:
        """The policy version captured in findings produced by this service."""

        return self._policy_version

    async def evaluate(
        self,
        event: PullRequestEvent,
        *,
        publish: bool = True,
        now: date | datetime | None = None,
        correlation_id: str | None = None,
    ) -> PRGuardianResult:
        """Evaluate one PR while keeping computation, recording, and output ordered."""

        if publish and (self._dependencies.findings is None or self._publisher is None):
            raise RuntimeError(
                "PR Guardian publishing requires a durable finding store and artifact outbox"
            )
        started = time.monotonic()
        config = self._config_for(event)
        review = self._preparer.prepare(event)
        workflow, policy = await self._dependencies.workflows.start_pr_review(
            service_id=review.primary_service,
            repository=event.repository,
            pr_number=event.number,
            assessment=review.assessment,
            simulated_policy=review.simulated_policy,
            correlation_id=correlation_id,
        )
        decision = enforcement_decision(
            config,
            review.assessment,
            review.filenames,
            _today(now),
            environ=self._dependencies.environ,
        )
        if review.company_context is not None and not review.company_context.qualified:
            decision = EnforcementDecision(
                False,
                REASON_CONTEXT_UNQUALIFIED,
                decision.rule,
            )
        conclusion: PublishConclusion = "failure" if decision.would_block else "neutral"
        finding = self._finding_factory.create(
            event=event,
            assessment=review.assessment,
            policy=policy,
            correlation_id=workflow.correlation_id,
            company_context=review.company_context,
        )
        if self._dependencies.findings is not None:
            self._dependencies.findings.record_finding(finding)
        publication_artifact_id: str | None = None
        if publish:
            if self._publisher is None:  # Defensive narrowing for static and runtime safety.
                raise RuntimeError("PR Guardian publication outbox is not configured")
            artifact = self._publisher.publish(
                event=event,
                assessment=review.assessment,
                workflow_id=workflow.workflow_id,
                correlation_id=workflow.correlation_id,
                changed_services=review.changed_services,
                policy=policy,
                mode=self.mode,
                conclusion=conclusion,
                enforcement=decision,
                company_context=review.company_context,
                now=now if isinstance(now, datetime) else None,
            )
            publication_artifact_id = artifact.artifact_id
        result = PRGuardianResult(
            assessment=review.assessment,
            policy=policy,
            workflow_id=workflow.workflow_id,
            correlation_id=workflow.correlation_id,
            conclusion=conclusion,
            changed_services=review.changed_services,
            changed_files=review.filenames,
            mode=self.mode,
            simulated_policy_would_block=policy.block_merge,
            repository_enforcement_would_block=decision.would_block,
            enforcement=decision,
            finding=finding,
            company_context=review.company_context,
            publication_artifact_id=publication_artifact_id,
        )
        self._telemetry_recorder.record(
            event=event,
            assessment=review.assessment,
            finding=finding,
            primary_service=review.primary_service,
            company_context=review.company_context,
            conclusion=conclusion,
            latency_ms=(time.monotonic() - started) * 1000.0,
        )
        return result

    def recover_pending_publications(self, *, maximum_deliveries: int = 100) -> int:
        """Deliver bounded due publication work already recorded in the outbox.

        This is intentionally explicit rather than an unbounded background loop.
        Operators or a scheduled worker invoke it to recover effects after a
        dependency outage or process failure.
        """

        if self._publisher is None:
            raise RuntimeError("PR Guardian publication outbox is not configured")
        return self._publisher.deliver_pending(maximum_deliveries=maximum_deliveries)

    def _config_for(self, event: PullRequestEvent) -> RepositoryConfig:
        config = self._dependencies.config or default_shadow_config(event.repository)
        if config.repository != event.repository:
            raise ValueError(
                "the loaded repository configuration names a different repository "
                f"({config.repository}) than the pull request ({event.repository})"
            )
        return config


def _today(now: date | datetime | None) -> date:
    if now is None:
        return datetime.now(timezone.utc).date()
    return now.date() if isinstance(now, datetime) else now
