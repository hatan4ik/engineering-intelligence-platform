"""Optional, non-executing output adapters for operational intelligence."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence

from integrations.azure_devops.deployment_failure import DeploymentFailureEvent
from integrations.github.pr_guardian import GitHubRestPRClient
from intelligence.deployment_failures import DeploymentFailureAnalysis
from intelligence.incidents import EvidenceEvent, IncidentAnalysis
from product.l2_proposals import L2Proposal, build_proposals


OPERATIONS_ISSUE_MARKER = "<!-- eip-operations-intelligence -->"


class GitHubIntelligenceClient(Protocol):
    """The narrow GitHub capability required to publish a maintenance issue."""

    def ensure_maintenance_issue(
        self,
        *,
        repository: str,
        marker: str,
        title: str,
        body: str,
        labels: tuple[str, ...] = (),
    ) -> int: ...


class NoOpOperationsPublisher:
    """The HTTP response carries the analysis; no external output is the default."""

    def publish(self, **_: object) -> None:
        return None


def github_intelligence_client(token: str) -> GitHubRestPRClient:
    """The existing REST client satisfies the narrow issue-publishing port."""

    return GitHubRestPRClient(token)


def _issue_body(
    header: str,
    analysis_lines: Sequence[str],
    proposals: Sequence[L2Proposal],
) -> str:
    lines = [header, "", "## Evidence-backed analysis (L1)", ""]
    lines.extend(f"- {line}" for line in analysis_lines)
    lines.extend(["", "## Proposals (L2 - requires human execution)", ""])
    for proposal in proposals:
        lines.append(f"### {proposal.kind}: {proposal.title}")
        lines.append(f"- Exact action: {proposal.exact_action}")
        lines.append(f"- Rollback path: {proposal.rollback_path}")
        lines.append(f"- Evidence: {', '.join(proposal.evidence_refs) or 'none'}")
        lines.append("")
    lines.append(
        "This platform proposes only. Every action above requires human execution; "
        "nothing here has been applied."
    )
    return "\n".join(lines)


@dataclass(frozen=True)
class GitHubIncidentPublisher:
    """Open/update one marked issue per repository with incident proposals."""

    client: GitHubIntelligenceClient
    repository: str
    environment: str = "unknown"

    def publish(
        self,
        *,
        incident_id: str,
        service: str,
        analysis: IncidentAnalysis,
        impacted_services: tuple[str, ...],
    ) -> None:
        proposals = build_proposals(analysis, service=service, environment=self.environment)
        lines = [f"impacted services: {', '.join(impacted_services)}"] + [
            f"{hypothesis.title} (confidence {hypothesis.confidence:.2f})"
            for hypothesis in analysis.hypotheses
        ]
        self.client.ensure_maintenance_issue(
            repository=self.repository,
            marker=OPERATIONS_ISSUE_MARKER,
            title=f"Incident {incident_id}: {service} operational intelligence",
            body=_issue_body(OPERATIONS_ISSUE_MARKER, lines, proposals),
            labels=("engineering-intelligence", "operational-intelligence"),
        )


@dataclass(frozen=True)
class GitHubDeploymentFailurePublisher:
    """Open/update one marked issue per repository with deployment proposals."""

    client: GitHubIntelligenceClient
    repository: str

    def publish(
        self,
        *,
        event: DeploymentFailureEvent,
        analysis: DeploymentFailureAnalysis,
        evidence: tuple[EvidenceEvent, ...] = (),
    ) -> None:
        proposals = build_proposals(
            analysis,
            service=event.service,
            environment=event.environment,
            evidence=evidence,
        )
        lines = list(analysis.facts) + [
            f"{hypothesis.title} (confidence {hypothesis.confidence:.2f})"
            for hypothesis in analysis.hypotheses
        ]
        self.client.ensure_maintenance_issue(
            repository=self.repository,
            marker=OPERATIONS_ISSUE_MARKER,
            title=(
                f"Deployment failure {analysis.deployment_id}: "
                f"{event.service} operational intelligence"
            ),
            body=_issue_body(OPERATIONS_ISSUE_MARKER, lines, proposals),
            labels=("engineering-intelligence", "operational-intelligence"),
        )
