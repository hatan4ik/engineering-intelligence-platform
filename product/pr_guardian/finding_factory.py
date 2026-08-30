"""Construction of immutable PR Guardian product findings."""

from __future__ import annotations

from intelligence.pr_guardian import PRPolicyDecision
from intelligence.risk import RiskAssessment
from integrations.github.pr_guardian import PullRequestEvent

from .company_brain import PRGuardianCompanyContext
from .contracts import EvidenceBasis, EvidenceBundle, FindingAction, PRFinding


class PRFindingFactory:
    """Create product findings without knowing about storage or publishing."""

    def __init__(self, *, policy_version: str) -> None:
        self._policy_version = policy_version

    def create(
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
        return PRFinding(
            finding_id=f"pr:{event.repository}:{event.number}:{event.head_sha}:risk",
            repository=event.repository,
            pr_number=event.number,
            head_sha=event.head_sha,
            severity=assessment.band,
            summary=f"Shadow risk score {assessment.score}/100 ({assessment.band}).",
            correlation_id=correlation_id,
            policy_version=self._policy_version,
            context_version=context_version,
            context_qualified=context_qualified,
            simulated_action=(
                _simulated_action(policy) if context_qualified else FindingAction.NONE
            ),
            evidence=evidence,
        )


def _simulated_action(policy: PRPolicyDecision) -> FindingAction:
    if policy.block_merge:
        return FindingAction.WOULD_BLOCK
    if policy.require_additional_approval:
        return FindingAction.ADDITIONAL_APPROVAL
    if policy.require_extended_tests:
        return FindingAction.EXTENDED_TESTS
    return FindingAction.NONE
