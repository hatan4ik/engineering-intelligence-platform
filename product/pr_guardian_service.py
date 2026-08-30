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

from company_brain.model import BrainPrincipal
from control_plane.workflows import ControlPlaneWorkflows
from intelligence.graph import ServiceGraph
from intelligence.pr_guardian import PRPolicyDecision
from intelligence.risk import RiskAssessment
from integrations.github.pr_guardian import GitHubPRClient, PullRequestEvent
from product.pr_guardian.company_brain import PRGuardianCompanyContext
from product.pr_guardian.config import default_shadow_config
from product.pr_guardian.contracts import PRFinding, RepositoryConfig
from product.pr_guardian.enforcement import (
    EnforcementDecision,
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
    conclusion: str
    changed_services: tuple[str, ...]
    changed_files: tuple[str, ...]
    mode: str
    would_block: bool
    enforcement: EnforcementDecision
    finding: PRFinding | None
    company_context: PRGuardianCompanyContext | None


class PRGuardianService:
    """Product use case for an evidence-backed GitHub PR risk check.

    GitHub is only an event/output adapter. Risk scoring remains deterministic,
    and the durable control plane records the exact assessment and policy plan.
    """

    def __init__(
        self,
        *,
        graph: ServiceGraph | None,
        github: GitHubPRClient,
        workflows: ControlPlaneWorkflows,
        history: HistoricalFailureProvider | None = None,
        telemetry: TelemetrySink | None = None,
        mode: str = "shadow",
        config: RepositoryConfig | None = None,
        environ: Mapping[str, str] | None = None,
        company_context: QualifiedCompanyContextProvider | None = None,
        principal: BrainPrincipal | None = None,
        findings: PRGuardianFindingStore | None = None,
        policy_version: str = "pr-policy-v1",
    ) -> None:
        # The mode is a property of the evaluated repository, not of this
        # process. Without a repository configuration the only defensible
        # answer is shadow, so a caller cannot request advisory or enforce
        # from a flag alone.
        if config is not None:
            resolved = str(config.mode)
        elif mode == "shadow":
            resolved = mode
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

        # Preserve these attributes as the injectable public dependencies for
        # existing callers, while focused components own their mechanisms.
        self.graph = graph
        self.github = github
        self.workflows = workflows
        self.history = history
        self.telemetry = telemetry or NullTelemetrySink()
        self.config = config
        self.environ = environ
        self.mode = resolved
        self.company_context = company_context
        self.principal = principal
        self.findings = findings
        self.policy_version = config.policy_version if config is not None else policy_version

        self._preparer = PRReviewPreparer(
            graph=graph,
            github=github,
            history=history,
            company_context=company_context,
            principal=principal,
        )
        self._finding_factory = PRFindingFactory(policy_version=self.policy_version)
        self._publisher = PRGuardianPublisher(github)
        self._telemetry_recorder = PRGuardianTelemetryRecorder(self.telemetry)

    async def evaluate(
        self,
        event: PullRequestEvent,
        *,
        publish: bool = True,
        now: date | datetime | None = None,
        correlation_id: str | None = None,
    ) -> PRGuardianResult:
        """Evaluate one PR while keeping computation, recording, and output ordered."""

        started = time.monotonic()
        config = self._config_for(event)
        review = self._preparer.prepare(event)
        workflow, policy = await self.workflows.start_pr_review(
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
            environ=self.environ,
        )
        if review.company_context is not None and not review.company_context.qualified:
            # A caller that asks the Company Brain to qualify its context
            # cannot fall back to raw graph data when that qualification fails.
            decision = EnforcementDecision(
                False,
                REASON_CONTEXT_UNQUALIFIED,
                decision.rule,
            )
        conclusion = "failure" if decision.would_block else "neutral"
        finding = self._finding_factory.create(
            event=event,
            assessment=review.assessment,
            policy=policy,
            correlation_id=workflow.correlation_id,
            company_context=review.company_context,
        )
        if self.findings is not None:
            self.findings.record_finding(finding)
        result = PRGuardianResult(
            assessment=review.assessment,
            policy=policy,
            workflow_id=workflow.workflow_id,
            correlation_id=workflow.correlation_id,
            conclusion=conclusion,
            changed_services=review.changed_services,
            changed_files=review.filenames,
            mode=self.mode,
            would_block=policy.block_merge,
            enforcement=decision,
            finding=finding,
            company_context=review.company_context,
        )
        if publish:
            self._publisher.publish(
                event=event,
                assessment=review.assessment,
                workflow_id=workflow.workflow_id,
                changed_services=review.changed_services,
                policy=policy,
                mode=self.mode,
                conclusion=conclusion,
                enforcement=decision,
                company_context=review.company_context,
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

    def _config_for(self, event: PullRequestEvent) -> RepositoryConfig:
        config = self.config or default_shadow_config(event.repository)
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
