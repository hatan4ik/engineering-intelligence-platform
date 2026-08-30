"""GitHub presentation stage for an already-recorded PR Guardian review."""

from __future__ import annotations

from intelligence.pr_guardian import PRPolicyDecision
from intelligence.risk import RiskAssessment
from integrations.github.pr_guardian import GitHubPRClient, PullRequestEvent
from product.pr_guardian_shadow import observation_comment, observation_from_assessment

from .company_brain import PRGuardianCompanyContext
from .contracts import ProductMode
from .enforcement import EnforcementDecision


class PRGuardianPublisher:
    """Render and publish one check/comment pair; it does not make decisions."""

    def __init__(self, github: GitHubPRClient) -> None:
        self._github = github

    def publish(
        self,
        *,
        event: PullRequestEvent,
        assessment: RiskAssessment,
        workflow_id: str,
        changed_services: tuple[str, ...],
        policy: PRPolicyDecision,
        mode: str,
        conclusion: str,
        enforcement: EnforcementDecision,
        company_context: PRGuardianCompanyContext | None,
    ) -> None:
        observation = observation_from_assessment(
            event=event,
            assessment=assessment,
            workflow_id=workflow_id,
            changed_services=changed_services,
            would_require_extended_tests=policy.require_extended_tests,
            would_require_additional_approval=policy.require_additional_approval,
            would_block=policy.block_merge,
            # The service has recorded the workflow, but the standalone
            # shadow runner is responsible for a full chain verification.
            # Do not claim that verification happened in this request path.
            audit_chain_verified=False,
            mode=mode,
            enforcement=enforcement.as_dict(),
        )
        summary = observation_comment(observation)
        if company_context is not None and not company_context.qualified:
            summary += (
                "\n\n> Company Brain context is insufficient for a simulated control. "
                "This observation remains neutral. "
                + " ".join(company_context.limitations)
            )
        self._github.publish_check(
            repository=event.repository,
            head_sha=event.head_sha,
            name=f"Engineering Intelligence / PR Guardian ({mode})",
            conclusion=conclusion,
            title=check_title(mode, assessment, enforcement),
            summary=summary,
        )
        self._github.publish_comment(
            repository=event.repository,
            pr_number=event.number,
            body=summary,
        )


def check_title(
    mode: str,
    assessment: RiskAssessment,
    decision: EnforcementDecision,
) -> str:
    """Render the check title from a decision the use case already made."""

    risk = f"{assessment.score}/100 ({assessment.band})"
    if mode == ProductMode.ADVISORY.value:
        return f"Advisory risk: {risk} — this check does not block merges"
    if mode == ProductMode.ENFORCE.value:
        if decision.would_block:
            return f"Blocked by {decision.rule}: risk {risk}"
        return f"Enforcing risk: {risk} — no blocking rule fired"
    return f"Shadow risk: {risk}"
