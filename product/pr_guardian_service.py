from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Mapping, Protocol

from control_plane.workflows import ControlPlaneWorkflows
from intelligence.extractors import service_from_path
from intelligence.graph import ServiceGraph
from intelligence.pr_guardian import PRPolicyDecision, render_markdown
from intelligence.risk import ChangeContext, RiskAssessment, assess_change
from integrations.github.pr_guardian import GitHubPRClient, PullRequestEvent
from product.pr_guardian.config import default_shadow_config
from product.pr_guardian.contracts import ProductMode, RepositoryConfig
from product.pr_guardian.enforcement import (
    EnforcementDecision,
    enforcement_decision,
    is_delivery_control_path,
    is_docs_path,
    is_iac_path,
    is_security_boundary_path,
    is_test_path,
)
from product.pr_guardian_shadow import observation_from_assessment, observation_comment
from telemetry.events import NullTelemetrySink, OperationEvent, TelemetrySink


class HistoricalFailureProvider(Protocol):
    def similar_failed_changes(self, *, repository: str, filenames: tuple[str, ...]) -> int: ...


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


class PRGuardianService:
    """Product workflow for an evidence-backed GitHub PR risk check.

    GitHub is only the event/output adapter. Risk scoring remains deterministic,
    and the durable control plane records the exact assessment and policy plan.
    """

    def __init__(
        self,
        *,
        graph: ServiceGraph,
        github: GitHubPRClient,
        workflows: ControlPlaneWorkflows,
        history: HistoricalFailureProvider | None = None,
        telemetry: TelemetrySink | None = None,
        mode: str = "shadow",
        config: RepositoryConfig | None = None,
        environ: Mapping[str, str] | None = None,
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
        self.graph = graph
        self.github = github
        self.workflows = workflows
        self.history = history
        self.telemetry = telemetry or NullTelemetrySink()
        self.config = config
        self.environ = environ
        self.mode = resolved

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
        known_services = set(self.graph.nodes)
        changed_services = tuple(sorted({
            service
            for path in filenames
            if (service := service_from_path(path, known_services)) is not None
        }))

        touches_iac = any(is_iac_path(path) for path in filenames)
        touches_delivery = any(is_delivery_control_path(path) for path in filenames)
        touches_security = any(is_security_boundary_path(path) for path in filenames)
        test_files = [path for path in filenames if is_test_path(path)]
        source_files = [path for path in filenames if not is_test_path(path) and not is_docs_path(path)]
        weak_test_evidence = bool(source_files) and not test_files
        unmapped_service_change = bool(source_files) and not changed_services
        similar_failures = (
            self.history.similar_failed_changes(repository=event.repository, filenames=filenames)
            if self.history
            else 0
        )

        assessment = assess_change(
            self.graph,
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

        primary_service = changed_services[0] if changed_services else "unknown"
        workflow, policy = await self.workflows.start_pr_review(
            service_id=primary_service,
            repository=event.repository,
            pr_number=event.number,
            assessment=assessment,
        )

        # Shadow and advisory modes make every published check neutral.  Only
        # enforce mode may fail, and only when the repository's own single
        # deterministic rule fired and no owner waiver covered the change.
        decision = enforcement_decision(
            config, assessment, filenames, _today(now), environ=self.environ
        )
        conclusion = "failure" if decision.would_block else "neutral"
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
            },
        ))
        return result


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
