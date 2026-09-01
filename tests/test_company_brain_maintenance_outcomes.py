"""A maintenance proposal only learns after explicit review and source observation."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from company_brain import (
    CompanyBrainMaintenanceError,
    EntityKind,
    MaintenanceOutcomeState,
    MaintenanceReviewDecision,
    MaintenanceReviewDisposition,
    MemoryMaintenanceAction,
    MemoryMaintenanceFindingKind,
    MemoryMaintenanceProposal,
    SourceRevisionObservation,
    evaluate_maintenance_outcome,
    parse_maintenance_proposal,
    parse_maintenance_review_decision,
    parse_source_revision_observation,
)
from scripts.validate_company_brain_maintenance_outcome import main


REVIEWED_AT = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)


def _proposal() -> MemoryMaintenanceProposal:
    return MemoryMaintenanceProposal(
        proposal_id="maintenance:payments-runbook-stale",
        tenant_id="tenant-acme",
        source_id="runbook:payments",
        source_kind=EntityKind.RUNBOOK,
        source_label="Restart payments",
        source_system="confluence",
        source_record_id="runbook-payments",
        source_revision="7",
        source_version=3,
        finding_kind=MemoryMaintenanceFindingKind.STALE,
        action=MemoryMaintenanceAction.REQUEST_OWNER_REVIEW,
        severity=4,
        reason="Source record is older than the approved freshness threshold.",
        policy_version="company-brain-maintenance-v1",
    )


def _decision(
    proposal: MemoryMaintenanceProposal,
    disposition: MaintenanceReviewDisposition = MaintenanceReviewDisposition.ACCEPTED,
) -> MaintenanceReviewDecision:
    return MaintenanceReviewDecision(
        decision_id="maintenance-decision:payments-review-1",
        proposal_id=proposal.proposal_id,
        tenant_id=proposal.tenant_id,
        source_id=proposal.source_id,
        source_system=proposal.source_system,
        source_record_id=proposal.source_record_id,
        source_revision=proposal.source_revision,
        source_version=proposal.source_version,
        disposition=disposition,
        reviewed_by="team:payments-owner",
        reviewed_at=REVIEWED_AT,
        rationale="The owner will refresh the authoritative runbook.",
    )


def _observation(proposal: MemoryMaintenanceProposal) -> SourceRevisionObservation:
    return SourceRevisionObservation(
        observation_id="maintenance-observation:payments-revision-8",
        tenant_id=proposal.tenant_id,
        source_id=proposal.source_id,
        source_system=proposal.source_system,
        source_record_id=proposal.source_record_id,
        observed_revision="8",
        observed_at=REVIEWED_AT + timedelta(hours=1),
        observed_by="team:documentation-audit",
        evidence_locator="evidence://confluence/runbook-payments/revision-8",
        evidence_digest="sha256:" + "a" * 64,
    )


def test_accepted_review_is_not_success_until_an_independent_source_revision_is_observed():
    proposal = _proposal()
    decision = _decision(proposal)

    awaiting = evaluate_maintenance_outcome(proposal, decision)
    verified = evaluate_maintenance_outcome(proposal, decision, _observation(proposal))

    assert (
        awaiting.state is MaintenanceOutcomeState.ACCEPTED_AWAITING_SOURCE_OBSERVATION
    )
    assert awaiting.source_change_verified is False
    assert awaiting.observation_id is None
    assert verified.state is MaintenanceOutcomeState.VERIFIED_SOURCE_REVISION
    assert verified.source_change_verified is True
    assert verified.observation_id == "maintenance-observation:payments-revision-8"


@pytest.mark.parametrize(
    ("disposition", "state"),
    [
        (MaintenanceReviewDisposition.REJECTED, MaintenanceOutcomeState.REJECTED),
        (MaintenanceReviewDisposition.EXPIRED, MaintenanceOutcomeState.EXPIRED),
    ],
)
def test_rejected_or_expired_decisions_are_explicit_non_success_outcomes(
    disposition, state
):
    proposal = _proposal()
    outcome = evaluate_maintenance_outcome(proposal, _decision(proposal, disposition))

    assert outcome.state is state
    assert outcome.source_change_verified is False
    assert outcome.independently_observed is False


def test_outcome_rejects_mismatched_or_nonindependent_source_observations():
    proposal = _proposal()
    decision = _decision(proposal)
    observation = _observation(proposal)

    with pytest.raises(
        CompanyBrainMaintenanceError, match="source_revision does not match"
    ):
        evaluate_maintenance_outcome(
            proposal,
            MaintenanceReviewDecision(
                **{**decision.__dict__, "source_revision": "incorrect"}
            ),
        )

    with pytest.raises(CompanyBrainMaintenanceError, match="revision different"):
        evaluate_maintenance_outcome(
            proposal,
            decision,
            SourceRevisionObservation(
                **{
                    **observation.__dict__,
                    "observed_revision": proposal.source_revision,
                }
            ),
        )

    with pytest.raises(CompanyBrainMaintenanceError, match="identity must differ"):
        evaluate_maintenance_outcome(
            proposal,
            decision,
            SourceRevisionObservation(
                **{**observation.__dict__, "observed_by": decision.reviewed_by}
            ),
        )

    with pytest.raises(CompanyBrainMaintenanceError, match="only an accepted decision"):
        evaluate_maintenance_outcome(
            proposal,
            _decision(proposal, MaintenanceReviewDisposition.REJECTED),
            observation,
        )


def test_parsers_and_cli_keep_external_outcome_payloads_bounded(tmp_path, capsys):
    proposal = _proposal()
    decision = _decision(proposal)
    observation = _observation(proposal)

    assert parse_maintenance_proposal(proposal.to_payload()) == proposal
    assert parse_maintenance_review_decision(decision.to_payload()) == decision
    assert parse_source_revision_observation(observation.to_payload()) == observation

    proposal_path = tmp_path / "proposal.json"
    decision_path = tmp_path / "decision.json"
    observation_path = tmp_path / "observation.json"
    proposal_path.write_text(json.dumps(proposal.to_payload()), encoding="utf-8")
    decision_path.write_text(json.dumps(decision.to_payload()), encoding="utf-8")
    observation_path.write_text(json.dumps(observation.to_payload()), encoding="utf-8")

    assert (
        main(
            [
                "--proposal",
                str(proposal_path),
                "--decision",
                str(decision_path),
                "--source-observation",
                str(observation_path),
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["source_change_verified"] is True
    assert payload["requires_human_review"] is True
