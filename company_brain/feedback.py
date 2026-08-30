"""Project shared product findings and explicit outcomes into Company Brain memory.

Product-specific adapters translate their records at this boundary. The
projector consequently has no dependency on PR Guardian (or a future product),
and it records metadata only; an evidence reference without its original ACL
is never copied into Company Brain evidence storage.
"""

from __future__ import annotations

from .model import BrainEntity, CompanyBrain, EntityKind, RelationshipKind
from .product_contracts import ProductFinding, ProductOutcome


class CompanyBrainFeedbackProjector:
    """Retain typed product learning records without inferring correctness."""

    def __init__(self, brain: CompanyBrain) -> None:
        self.brain = brain

    def project_finding(self, finding: ProductFinding) -> str:
        """Project a bounded product finding without importing a product package."""

        self.brain.upsert_entity(finding.scope.as_entity())
        self.brain.upsert_entity(finding.subject.as_entity())
        finding_id = f"finding:{finding.finding_id}"
        self.brain.upsert_entity(
            BrainEntity(
                entity_id=finding_id,
                kind=EntityKind.FINDING,
                label=finding.summary,
                attributes=(
                    ("assessment_version", finding.provenance.assessment_version),
                    ("context_qualified", str(finding.provenance.context_qualified).lower()),
                    ("context_version", finding.provenance.context_version),
                    ("evidence_basis", finding.evidence.basis.value),
                    ("product", finding.product),
                    ("recommendation", finding.recommendation),
                    ("severity", finding.severity),
                ),
            )
        )
        self.brain.relate(
            source_id=finding.scope.entity_id,
            target_id=finding.subject.entity_id,
            kind=finding.scope_relationship,
        )
        self.brain.relate(
            source_id=finding.subject.entity_id,
            target_id=finding_id,
            kind=RelationshipKind.ASSESSED_BY,
        )
        return finding_id

    def project_outcome(self, outcome: ProductOutcome) -> str:
        """Attach one explicit product outcome to a previously projected finding."""

        finding_id = f"finding:{outcome.finding_id}"
        if finding_id not in self.brain.entities:
            raise ValueError("a product finding must exist before its outcome is recorded")
        outcome_id = f"outcome:{outcome.outcome_id}"
        attributes = [
            ("disposition", outcome.disposition),
            ("outcome_kind", outcome.outcome_kind),
        ]
        if outcome.recorded_by:
            attributes.append(("recorded_by", outcome.recorded_by))
        if outcome.correlation_id:
            attributes.append(("correlation_id", outcome.correlation_id))
        self.brain.upsert_entity(
            BrainEntity(
                entity_id=outcome_id,
                kind=EntityKind.OUTCOME,
                label=f"{outcome.outcome_kind}: {outcome.disposition}",
                attributes=tuple(sorted(attributes)),
            )
        )
        self.brain.relate(source_id=finding_id, target_id=outcome_id, kind=RelationshipKind.HAS_OUTCOME)
        return outcome_id
