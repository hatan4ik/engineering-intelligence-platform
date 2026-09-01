"""Promotion review stays a human decision even after feedback is complete."""

from __future__ import annotations

import copy
import json
from datetime import date

import pytest

from company_brain.product_contracts import EvidenceBasis
from feedback.pr_guardian_promotion import (
    AdvisoryPromotionReviewPacket,
    PromotionReviewPacketError,
    REQUIRED_REVIEW_ROLES,
    RetainedEvidencePurpose,
    RetainedEvidenceReference,
    feedback_summary_from_shadow_report,
    parse_advisory_promotion_review_packet,
    validate_packet_against_shadow_report,
)
from feedback.pr_guardian_shadow import (
    build_shadow_report,
    canonical_json_sha256,
    canonical_shadow_outcomes_sha256,
)
from intelligence.risk import RiskAssessment, RiskFactor
from integrations.github.pr_guardian import PullRequestEvent
from product.pr_guardian_shadow import closure_outcome, observation_from_assessment
from scripts.validate_pr_guardian_promotion_packet import main


def _outcome(*, number: int, would_block: bool, label: str):
    sha = f"{number:08x}"
    observation = observation_from_assessment(
        event=PullRequestEvent("acme/payments", number, sha, "synchronize"),
        assessment=RiskAssessment(
            score=90 if would_block else 20,
            band="critical" if would_block else "moderate",
            blast_radius=("payments",),
            factors=(
                RiskFactor("security-boundary-change", 20, "identity controls changed"),
            ),
        ),
        workflow_id=f"pr:acme/payments:{number}",
        changed_services=("payments",),
        would_require_extended_tests=True,
        would_require_additional_approval=would_block,
        would_block=would_block,
        audit_chain_verified=True,
        observed_at="2026-09-01T12:00:00+00:00",
    )
    return closure_outcome(
        payload={
            "action": "closed",
            "number": number,
            "repository": {"full_name": "acme/payments"},
            "pull_request": {
                "head": {"sha": sha},
                "merged": True,
                "labels": [{"name": f"eip-pr-guardian/{label}"}],
            },
        },
        observation=observation,
        recorded_at="2026-09-01T12:30:00+00:00",
    )


def _candidate_records():
    records = []
    for number in range(1, 21):
        records.append(
            _outcome(number=number, would_block=True, label="confirmed-risk")
        )
    for number in range(21, 26):
        records.append(
            _outcome(number=number, would_block=True, label="false-positive")
        )
    for number in range(26, 31):
        records.append(
            _outcome(number=number, would_block=False, label="false-positive")
        )
    return records


def _report():
    return build_shadow_report(_candidate_records())


def _reference(
    *,
    evidence_id: str,
    purpose: RetainedEvidencePurpose,
    digest: str,
    basis: EvidenceBasis = EvidenceBasis.MEASURED,
    verifier: str | None = None,
) -> RetainedEvidenceReference:
    return RetainedEvidenceReference(
        evidence_id=evidence_id,
        purpose=purpose,
        basis=basis,
        source_system="enterprise-evidence-registry",
        locator=f"evidence://pr-guardian/payments/{evidence_id}",
        content_digest=digest,
        retention_days=365,
        access_control_ref="policy://data-governance/internal",
        immutability_control_ref="control://records/worm-v1",
        produced_by="team:platform",
        independently_verified_by=verifier,
    )


def _packet(report: dict[str, object] | None = None) -> AdvisoryPromotionReviewPacket:
    shadow_report = _report() if report is None else report
    feedback = feedback_summary_from_shadow_report(
        shadow_report,
        report_evidence_id="evidence:report",
        outcome_export_evidence_id="evidence:outcomes",
    )
    evidence = (
        _reference(
            evidence_id="evidence:citation",
            purpose=RetainedEvidencePurpose.CITATION_QUALITY_REVIEW,
            digest="sha256:" + "1" * 64,
        ),
        _reference(
            evidence_id="evidence:correlation",
            purpose=RetainedEvidencePurpose.INDEPENDENT_POST_MERGE_CORRELATION,
            digest="sha256:" + "2" * 64,
            verifier="team:sre",
        ),
        _reference(
            evidence_id="evidence:outcomes",
            purpose=RetainedEvidencePurpose.SHADOW_OUTCOME_EXPORT,
            digest=feedback.outcome_export_digest,
        ),
        _reference(
            evidence_id="evidence:performance",
            purpose=RetainedEvidencePurpose.PERFORMANCE_AND_COST_REPORT,
            digest="sha256:" + "3" * 64,
            basis=EvidenceBasis.DERIVED,
        ),
        _reference(
            evidence_id="evidence:report",
            purpose=RetainedEvidencePurpose.SHADOW_REPORT,
            digest=feedback.report_digest,
            basis=EvidenceBasis.DERIVED,
        ),
    )
    return AdvisoryPromotionReviewPacket(
        pilot_id="pr-guardian-payments",
        repository="acme/payments",
        policy_version="pr-policy-2026-09",
        pilot_manifest_digest="sha256:" + "4" * 64,
        runtime_configuration_digest="sha256:" + "5" * 64,
        prepared_on="2026-08-01",
        review_expires_on="2026-12-01",
        feedback=feedback,
        retained_evidence=evidence,
    )


def test_report_fingerprints_its_validated_outcome_export_independent_of_input_order():
    records = _candidate_records()
    report = build_shadow_report(records)

    assert report["input_provenance"] == {
        "canonical_outcome_export_sha256": canonical_shadow_outcomes_sha256(
            [record for record in reversed(records)]
        ),
        "closure_records": 30,
        "canonicalization": "validated closure records sorted by repository, PR, head SHA, and recorded_at",
    }


def test_complete_packet_binds_the_generated_report_but_never_grants_authority():
    report = _report()
    packet = _packet(report)

    parsed = parse_advisory_promotion_review_packet(
        packet.to_payload(), today=date(2026, 9, 1)
    )
    validate_packet_against_shadow_report(parsed, report)

    assert parsed.feedback.report_digest == canonical_json_sha256(report)
    assert parsed.required_review_roles == REQUIRED_REVIEW_ROLES
    assert parsed.advisory_or_enforcement_authorized is False
    assert parsed.runtime_mode == "shadow"
    assert parsed.review_state == "human-review-required"


def test_packet_rejects_digest_mismatch_and_expired_review_window():
    packet = _packet()
    payload = packet.to_payload()
    feedback = payload["feedback"]
    assert isinstance(feedback, dict)
    feedback["report_digest"] = "sha256:" + "0" * 64

    with pytest.raises(
        PromotionReviewPacketError, match="digest does not match feedback"
    ):
        parse_advisory_promotion_review_packet(payload, today=date(2026, 9, 1))

    payload = packet.to_payload()
    payload["review_expires_on"] = "2026-08-31"
    with pytest.raises(PromotionReviewPacketError, match="has expired"):
        parse_advisory_promotion_review_packet(payload, today=date(2026, 9, 1))


def test_packet_rejects_an_advisory_runtime_claim_and_nonindependent_correlation():
    packet = _packet()
    payload = packet.to_payload()
    payload["runtime_mode"] = "advisory"

    with pytest.raises(PromotionReviewPacketError, match="runtime_mode must be shadow"):
        parse_advisory_promotion_review_packet(payload, today=date(2026, 9, 1))

    with pytest.raises(PromotionReviewPacketError, match="verifier must differ"):
        _reference(
            evidence_id="evidence:bad-correlation",
            purpose=RetainedEvidencePurpose.INDEPENDENT_POST_MERGE_CORRELATION,
            digest="sha256:" + "9" * 64,
            verifier="team:platform",
        )


def test_report_binding_refuses_a_tampered_generated_report():
    report = _report()
    packet = _packet(report)
    tampered = copy.deepcopy(report)
    sample = tampered["sample"]
    assert isinstance(sample, dict)
    sample["confirmed_risks"] = 19

    with pytest.raises(PromotionReviewPacketError, match="does not match"):
        validate_packet_against_shadow_report(packet, tampered)


def test_cli_binds_a_packet_to_a_generated_report(tmp_path, capsys):
    report = _report()
    packet = _packet(report)
    packet_path = tmp_path / "packet.json"
    report_path = tmp_path / "report.json"
    packet_path.write_text(json.dumps(packet.to_payload()), encoding="utf-8")
    report_path.write_text(json.dumps(report), encoding="utf-8")

    assert (
        main(["--packet", str(packet_path), "--shadow-report", str(report_path)]) == 0
    )
    assert "advisory_or_enforcement_authorized=False" in capsys.readouterr().out
