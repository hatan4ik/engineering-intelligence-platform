from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from control_plane.workflows import ControlPlaneWorkflows
from intelligence.extractors import service_from_path
from intelligence.graph import ServiceGraph
from intelligence.pr_guardian import PRPolicyDecision, render_markdown
from intelligence.risk import ChangeContext, RiskAssessment, assess_change
from integrations.github.pr_guardian import GitHubPRClient, PullRequestEvent


class HistoricalFailureProvider(Protocol):
    def similar_failed_changes(self, *, repository: str, filenames: tuple[str, ...]) -> int: ...


@dataclass(frozen=True)
class PRGuardianResult:
    assessment: RiskAssessment
    policy: PRPolicyDecision
    workflow_id: str
    conclusion: str
    changed_services: tuple[str, ...]


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
    ) -> None:
        self.graph = graph
        self.github = github
        self.workflows = workflows
        self.history = history

    def evaluate(self, event: PullRequestEvent) -> PRGuardianResult:
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

        markdown = render_markdown(assessment)
        summary = (
            f"Changed services: {', '.join(changed_services) if changed_services else 'unmapped'}\n\n"
            + markdown
        )
        conclusion = "failure" if policy.block_merge else "neutral" if policy.require_additional_approval else "success"
        self.github.publish_check(
            repository=event.repository,
            head_sha=event.head_sha,
            name="Engineering Intelligence / PR Guardian",
            conclusion=conclusion,
            title=f"Change risk: {assessment.score}/100 ({assessment.band})",
            summary=summary,
        )
        self.github.publish_comment(
            repository=event.repository,
            pr_number=event.number,
            body=summary,
        )
        return PRGuardianResult(
            assessment=assessment,
            policy=policy,
            workflow_id=workflow.workflow_id,
            conclusion=conclusion,
            changed_services=changed_services,
        )


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
