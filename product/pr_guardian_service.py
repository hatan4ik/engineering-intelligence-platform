from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Mapping, Protocol

from company_brain.model import BrainPrincipal
from control_plane.workflows import ControlPlaneWorkflows
from intelligence.extractors import service_from_path
from intelligence.graph import ServiceGraph
from intelligence.pr_guardian import PRPolicyDecision, policy_for, render_markdown
from intelligence.risk import ChangeContext, RiskAssessment, assess_change
from integrations.github.pr_guardian import GitHubPRClient, PullRequestEvent
from product.pr_guardian.config import default_shadow_config
from product.pr_guardian.company_brain import PRGuardianCompanyContext
from product.pr_guardian.contracts import (
    EvidenceBasis,
    EvidenceBundle,
    FindingAction,
    PRFinding,
    ProductMode,
    RepositoryConfig,
)
from product.pr_guardian.enforcement import (
    EnforcementDecision,
    REASON_CONTEXT_UNQUALIFIED,
    enforcement_decision,
    is_delivery_control_path,
    is_docs_path,
    is_iac_path,
    is_security_boundary_path,
    is_test_path,
)
from product.pr_guardian.store import PRGuardianFindingStore
from product.pr_guardian_shadow import observation_from_assessment, observation_comment
from telemetry.events import NullTelemetrySink, OperationEvent, TelemetrySink


class HistoricalFailureProvider(Protocol):
    def similar_failed_changes(self, *, repository: str, filenames: tuple[str, ...]) -> int: ...


class QualifiedCompanyContextProvider(Protocol):
    """Read-only, qualified Company Brain context used by the PR product."""

    def known_services(self, *, repository: str, principal: BrainPrincipal) -> tuple[str, ...]: ...

    def context_for(
        self,
        *,
        repository: str,
        changed_services: tuple[str, ...],
        principal: BrainPrincipal,
    ) -> PRGuardianCompanyContext: ...


@dataclass(frozen=True)
class PRGuardianResult:
    assessment: RiskAssessment
    policy: PRPolicyDecision
    workflow_id: str
    conclusion: str
    changed_services: tuple[str, ...]
    changed_files: tuple[str, ...]
    mode: str
    would_block: bool
    enforcement: EnforcementDecision
    finding: PRFinding | None
    company_context: PRGuardianCompanyContext | None


class PRGuardianService:
    """Product workflow for an evidence-backed GitHub PR risk check.

    GitHub is only the event/output adapter. Risk scoring remains deterministic,
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
        # process.  Without a repository configuration the only defensible
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

    async def evaluate(
        self,
        event: PullRequestEvent,
        *,
        publish: bool = True,
        now: date | datetime | None = None,
    ) -> PRGuardianResult:
        started = time.monotonic()
        config = self.config or default_shadow_config(event.repository)
        if config.repository != event.repository:
            raise ValueError(
                "the loaded repository configuration names a different repository "
                f"({config.repository}) than the pull request ({event.repository})"
            )
        files = self.github.list_changed_files(event.repository, event.number)
        filenames = tuple(item.filename for item in files)
        known_services = (
            set(self.company_context.known_services(repository=event.repository, principal=self.principal))
            if self.company_context is not None and self.principal is not None
            else set(self.graph.nodes if self.graph is not None else ())
        )
        candidate_changed_services = tuple(sorted({
            service
            for path in filenames
            if (service := service_from_path(path, known_services)) is not None
        }))
        company_context = (
            self.company_context.context_for(
                repository=event.repository,
                changed_services=candidate_changed_services,
                principal=self.principal,
            )
            if self.company_context is not None and self.principal is not None
            else None
        )
        graph = company_context.graph if company_context is not None else self.graph
        if graph is None:  # Guarded by construction; makes static safety explicit.
            raise RuntimeError("PR Guardian graph is unavailable")
        changed_services = (
            company_context.changed_services if company_context is not None else candidate_changed_services
        )

        touches_iac = any(is_iac_path(path) for path in filenames)
        touches_delivery = any(is_delivery_control_path(path) for path in filenames)
        touches_security = any(is_security_boundary_path(path) for path in filenames)
        test_files = [path for path in filenames if is_test_path(path)]
        source_files = [path for path in filenames if not is_test_path(path) and not is_docs_path(path)]
        weak_test_evidence = bool(source_files) and not test_files
        unmapped_service_change = bool(source_files) and (
            not candidate_changed_services
            or (company_context is not None and not company_context.qualified)
        )
        similar_failures = (
            self.history.similar_failed_changes(repository=event.repository, filenames=filenames)
            if self.history
            else 0
        )

        assessment = assess_change(
            graph,
            ChangeContext(
                changed_services=changed_services,
                files_changed=len(files),
                touches_iac=touches_iac,
                touches_identity_or_security=touches_security,
                touches_delivery_pipeline=touches_delivery,
                unmapped_service_change=unmapped_service_change,
                weak_test_evidence=weak_test_evidence,
                similar_failed_changes=similar_failures,
            ),
        )

        # An unqualified world-model context may surface a risk observation,
        # but it cannot simulate a control.  This keeps missing/stale/conflicted
        # Company Brain evidence visible without turning it into a merge signal.
        simulated_policy = policy_for(assessment)
        if company_context is not None and not company_context.qualified:
            simulated_policy = PRPolicyDecision(False, False, False)

        primary_service = changed_services[0] if changed_services else "unknown"
        workflow, policy = await self.workflows.start_pr_review(
            service_id=primary_service,
            repository=event.repository,
            pr_number=event.number,
            assessment=assessment,
            simulated_policy=simulated_policy,
        )

        # Shadow and advisory modes make every published check neutral.  Only
        # enforce mode may fail, and only when the repository's own single
        # deterministic rule fired and no owner waiver covered the change.
        decision = enforcement_decision(
            config, assessment, filenames, _today(now), environ=self.environ
        )
        if company_context is not None and not company_context.qualified:
            # A caller that asks the Company Brain to qualify its context
            # cannot fall back to raw graph data when that qualification fails.
            decision = EnforcementDecision(False, REASON_CONTEXT_UNQUALIFIED, decision.rule)
        conclusion = "failure" if decision.would_block else "neutral"
        finding = self._finding(
            event=event,
            assessment=assessment,
            policy=policy,
            correlation_id=workflow.correlation_id,
            company_context=company_context,
        )
        if self.findings is not None:
            self.findings.record_finding(finding)
        result = PRGuardianResult(
            assessment=assessment,
            policy=policy,
            workflow_id=workflow.workflow_id,
            conclusion=conclusion,
            changed_services=changed_services,
            changed_files=filenames,
            mode=self.mode,
            would_block=policy.block_merge,
            enforcement=decision,
            finding=finding,
            company_context=company_context,
        )
        if publish:
            observation = observation_from_assessment(
                event=event,
                assessment=assessment,
                workflow_id=workflow.workflow_id,
                changed_services=changed_services,
                would_require_extended_tests=policy.require_extended_tests,
                would_require_additional_approval=policy.require_additional_approval,
                would_block=policy.block_merge,
                # The service has recorded the workflow, but the standalone
                # shadow runner is responsible for a full chain verification.
                # Do not claim that verification happened in this request path.
                audit_chain_verified=False,
                mode=self.mode,
                enforcement=decision.as_dict(),
            )
            # observation_comment is the single rendering path: it states the
            # authority this repository's mode actually has.
            summary = observation_comment(observation)
            if company_context is not None and not company_context.qualified:
                summary += (
                    "\n\n> Company Brain context is insufficient for a simulated control. "
                    "This observation remains neutral. "
                    + " ".join(company_context.limitations)
                )
            self.github.publish_check(
                repository=event.repository,
                head_sha=event.head_sha,
                name=f"Engineering Intelligence / PR Guardian ({self.mode})",
                conclusion=conclusion,
                title=_check_title(self.mode, assessment, decision),
                summary=summary,
            )
            self.github.publish_comment(
                repository=event.repository,
                pr_number=event.number,
                body=summary,
            )
        self.telemetry.emit(OperationEvent(
            correlation_id=workflow.correlation_id,
            operation="pr-guardian-review",
            component="product.pr_guardian",
            outcome=conclusion,
            latency_ms=(time.monotonic() - started) * 1000.0,
            repo=event.repository,
            service=primary_service,
            agent="pr-guardian",
            attributes={
                "pr": str(event.number),
                "head_sha": event.head_sha,
                "score": str(assessment.score),
                "band": assessment.band,
                "company_brain_context": "qualified" if company_context and company_context.qualified else "unqualified",
                "context_version": finding.context_version,
            },
        ))
        return result

    def _finding(
        self,
        *,
        event: PullRequestEvent,
        assessment: RiskAssessment,
        policy: PRPolicyDecision,
        correlation_id: str,
        company_context: PRGuardianCompanyContext | None,
    ) -> PRFinding:
        if company_context is None:
            evidence = EvidenceBundle(
                basis=EvidenceBasis.DERIVED,
                references=(),
                limitations=("No qualified Company Brain context was configured for this observation.",),
            )
            context_version = "legacy-graph:v1"
            context_qualified = False
        else:
            evidence = company_context.evidence
            context_version = company_context.context_version
            context_qualified = company_context.qualified
        action = _simulated_action(policy) if context_qualified else FindingAction.NONE
        return PRFinding(
            finding_id=f"pr:{event.repository}:{event.number}:{event.head_sha}:risk",
            repository=event.repository,
            pr_number=event.number,
            head_sha=event.head_sha,
            severity=assessment.band,
            summary=f"Shadow risk score {assessment.score}/100 ({assessment.band}).",
            correlation_id=correlation_id,
            policy_version=self.policy_version,
            context_version=context_version,
            context_qualified=context_qualified,
            simulated_action=action,
            evidence=evidence,
        )


def _check_title(mode: str, assessment: RiskAssessment, decision: EnforcementDecision) -> str:
    risk = f"{assessment.score}/100 ({assessment.band})"
    if mode == ProductMode.ADVISORY.value:
        return f"Advisory risk: {risk} — this check does not block merges"
    if mode == ProductMode.ENFORCE.value:
        if decision.would_block:
            return f"Blocked by {decision.rule}: risk {risk}"
        return f"Enforcing risk: {risk} — no blocking rule fired"
    return f"Shadow risk: {risk}"


def _today(now: date | datetime | None) -> date:
    if now is None:
        return datetime.now(timezone.utc).date()
    return now.date() if isinstance(now, datetime) else now
def _simulated_action(policy: PRPolicyDecision) -> FindingAction:
    if policy.block_merge:
        return FindingAction.WOULD_BLOCK
    if policy.require_additional_approval:
        return FindingAction.ADDITIONAL_APPROVAL
    if policy.require_extended_tests:
        return FindingAction.EXTENDED_TESTS
    return FindingAction.NONE
