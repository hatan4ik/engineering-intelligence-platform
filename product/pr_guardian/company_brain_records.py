"""Translate PR Guardian records into product-neutral Company Brain contracts."""

from __future__ import annotations

from company_brain.model import EntityKind, RelationshipKind
from company_brain.product_contracts import (
    FindingProvenance,
    ProductFinding,
    ProductOutcome,
    ProductSubject,
)
from company_brain.projector import repository_id

from .contracts import FindingOutcome, PRFinding


def finding_record(finding: PRFinding, *, provider: str = "github") -> ProductFinding:
    """Map one PR-specific observation into the Company Brain finding envelope."""

    scope = ProductSubject(
        entity_id=repository_id(provider=provider, repository=finding.repository),
        kind=EntityKind.REPOSITORY,
        label=finding.repository,
        attributes=(("provider", provider),),
    )
    subject = ProductSubject(
        entity_id=f"pr-change:{finding.repository}:{finding.pr_number}:{finding.head_sha}",
        kind=EntityKind.CHANGE,
        label=f"PR #{finding.pr_number} at {finding.head_sha}",
        attributes=(
            ("head_sha", finding.head_sha),
            ("pr_number", str(finding.pr_number)),
            ("repository", finding.repository),
        ),
    )
    return ProductFinding(
        finding_id=finding.finding_id,
        product="pr-guardian",
        scope=scope,
        subject=subject,
        scope_relationship=RelationshipKind.CHANGED_BY,
        severity=finding.severity,
        summary=finding.summary,
        correlation_id=finding.correlation_id,
        evidence=finding.evidence,
        provenance=FindingProvenance(
            assessment_version=finding.policy_version,
            context_version=finding.context_version,
            context_qualified=finding.context_qualified,
        ),
        recommendation=finding.simulated_action.value,
    )


def outcome_records(outcome: FindingOutcome) -> tuple[ProductOutcome, ProductOutcome]:
    """Preserve PR risk and utility dispositions as independently queryable outcomes."""

    correlation = outcome.post_merge_correlation_id
    suffix = correlation or "unlinked"
    return (
        ProductOutcome(
            outcome_id=(
                f"pr-guardian:{outcome.finding_id}:reviewer-risk:"
                f"{outcome.reviewer_risk.value}:{suffix}"
            ),
            finding_id=outcome.finding_id,
            outcome_kind="reviewer-risk",
            disposition=outcome.reviewer_risk.value,
            recorded_by=outcome.recorded_by,
            correlation_id=correlation,
        ),
        ProductOutcome(
            outcome_id=(
                f"pr-guardian:{outcome.finding_id}:reviewer-utility:"
                f"{outcome.reviewer_utility.value}:{suffix}"
            ),
            finding_id=outcome.finding_id,
            outcome_kind="reviewer-utility",
            disposition=outcome.reviewer_utility.value,
            recorded_by=outcome.recorded_by,
            correlation_id=correlation,
        ),
    )
