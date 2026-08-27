"""Project PR findings and explicit outcomes into Company Brain memory.

The product contracts intentionally expose only already-authorized evidence
references. This projector records finding/outcome metadata but does not copy
those references into the Company Brain without the original source ACL.
"""

from __future__ import annotations

from product.pr_guardian.contracts import FindingOutcome, PRFinding

from .model import BrainEntity, CompanyBrain, EntityKind, RelationshipKind
from .projector import repository_id


class CompanyBrainFeedbackProjector:
    """Retain reviewable PR learning records without inferring correctness."""

    def __init__(self, brain: CompanyBrain, *, provider: str = "github") -> None:
        self.brain = brain
        self.provider = provider

    def project_finding(self, finding: PRFinding) -> str:
        repository = repository_id(provider=self.provider, repository=finding.repository)
        if repository not in self.brain.entities:
            self.brain.upsert_entity(
                BrainEntity(
                    entity_id=repository,
                    kind=EntityKind.REPOSITORY,
                    label=finding.repository,
                    attributes=(("provider", self.provider),),
                )
            )
        change_id = f"pr-change:{finding.repository}:{finding.pr_number}:{finding.head_sha}"
        finding_id = f"finding:{finding.finding_id}"
        self.brain.upsert_entity(
            BrainEntity(
                entity_id=change_id,
                kind=EntityKind.CHANGE,
                label=f"PR #{finding.pr_number} at {finding.head_sha}",
                attributes=(
                    ("head_sha", finding.head_sha),
                    ("pr_number", str(finding.pr_number)),
                    ("repository", finding.repository),
                ),
            )
        )
        self.brain.upsert_entity(
            BrainEntity(
                entity_id=finding_id,
                kind=EntityKind.FINDING,
                label=finding.summary,
                attributes=(
                    ("context_qualified", str(finding.context_qualified).lower()),
                    ("context_version", finding.context_version),
                    ("evidence_basis", finding.evidence.basis.value),
                    ("policy_version", finding.policy_version),
                    ("severity", finding.severity),
                    ("simulated_action", finding.simulated_action.value),
                ),
            )
        )
        self.brain.relate(source_id=repository, target_id=change_id, kind=RelationshipKind.CHANGED_BY)
        self.brain.relate(source_id=change_id, target_id=finding_id, kind=RelationshipKind.ASSESSED_BY)
        return finding_id

    def project_outcome(self, outcome: FindingOutcome) -> str:
        finding_id = f"finding:{outcome.finding_id}"
        if finding_id not in self.brain.entities:
            raise ValueError("a PR finding must exist before its outcome is recorded")
        correlation = outcome.post_merge_correlation_id or "unlinked"
        outcome_id = (
            f"outcome:{outcome.finding_id}:{outcome.reviewer_risk.value}:"
            f"{outcome.reviewer_utility.value}:{correlation}"
        )
        attributes = [
            ("reviewer_risk", outcome.reviewer_risk.value),
            ("reviewer_utility", outcome.reviewer_utility.value),
        ]
        if outcome.recorded_by:
            attributes.append(("recorded_by", outcome.recorded_by))
        if outcome.post_merge_correlation_id:
            attributes.append(("post_merge_correlation_id", outcome.post_merge_correlation_id))
        self.brain.upsert_entity(
            BrainEntity(
                entity_id=outcome_id,
                kind=EntityKind.OUTCOME,
                label=f"PR finding outcome: {outcome.reviewer_risk.value}",
                attributes=tuple(sorted(attributes)),
            )
        )
        self.brain.relate(source_id=finding_id, target_id=outcome_id, kind=RelationshipKind.HAS_OUTCOME)
        return outcome_id
