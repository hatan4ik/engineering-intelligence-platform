from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Protocol

from control_plane.workflows import ControlPlaneWorkflows
from intelligence.extractors import service_from_path
from intelligence.graph import ServiceGraph
from intelligence.pr_guardian import PRPolicyDecision, render_markdown
from intelligence.risk import ChangeContext, RiskAssessment, assess_change
from integrations.github.pr_guardian import GitHubPRClient, PullRequestEvent
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
    mode: str
    would_block: bool


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
    ) -> None:
        if mode != "shadow":
            raise ValueError("PR Guardian supports only non-blocking shadow mode")
        self.graph = graph
        self.github = github
        self.workflows = workflows
        self.history = history
        self.telemetry = telemetry or NullTelemetrySink()
        self.mode = mode

    def evaluate(self, event: PullRequestEvent, *, publish: bool = True) -> PRGuardianResult:
        started = time.monotonic()
        files = self.github.list_changed_files(event.repository, event.number)
        filenames = tuple(item.filename for item in files)
        known_services = set(self.graph.nodes)
        changed_services = tuple(sorted({
            service
            for path in filenames
            if (service := service_from_path(path, known_services)) is not None
        }))

        touches_iac = any(_is_iac(path) for path in filenames)
        touches_delivery = any(_is_delivery_control(path) for path in filenames)
        touches_security = any(_is_security_boundary(path) for path in filenames)
        test_files = [path for path in filenames if _is_test(path)]
        source_files = [path for path in filenames if not _is_test(path) and not _is_docs(path)]
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
        workflow, policy = self.workflows.start_pr_review(
            service_id=primary_service,
            repository=event.repository,
            pr_number=event.number,
            assessment=assessment,
        )

        # Shadow mode intentionally makes every published check neutral.  The
        # policy remains visible only as a simulated "would" decision.
        conclusion = "neutral"
        result = PRGuardianResult(
            assessment=assessment,
            policy=policy,
            workflow_id=workflow.workflow_id,
            conclusion=conclusion,
            changed_services=changed_services,
            mode=self.mode,
            would_block=policy.block_merge,
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
            )
            summary = observation_comment(observation)
            self.github.publish_check(
                repository=event.repository,
                head_sha=event.head_sha,
                name="Engineering Intelligence / PR Guardian (shadow)",
                conclusion=conclusion,
                title=f"Shadow risk: {assessment.score}/100 ({assessment.band})",
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


def _is_test(path: str) -> bool:
    lowered = path.lower()
    return "/test" in lowered or lowered.startswith("test") or lowered.endswith(("_test.py", ".spec.ts", ".test.ts", ".spec.js", ".test.js"))


def _is_docs(path: str) -> bool:
    lowered = path.lower()
    return lowered.endswith((".md", ".rst", ".txt")) or lowered.startswith("docs/")


def _is_iac(path: str) -> bool:
    lowered = path.lower()
    return lowered.endswith((".tf", ".tfvars")) or lowered.startswith(("infra/", "terraform/", "helm/", "k8s/"))


def _is_delivery_control(path: str) -> bool:
    lowered = path.lower()
    return lowered.startswith((".github/workflows/", "pipelines/", "azure-pipelines")) or lowered.endswith(("azure-pipelines.yml", "jenkinsfile"))


def _is_security_boundary(path: str) -> bool:
    lowered = path.lower()
    markers = ("iam", "rbac", "identity", "auth", "security", "policy", "keyvault", "key_vault", "networkpolicy")
    return any(marker in lowered for marker in markers)
