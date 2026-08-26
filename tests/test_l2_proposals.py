"""L2 = propose, never execute. These tests pin that boundary."""
from datetime import datetime, timedelta, timezone

import pytest

from intelligence.deployment_failures import investigate_deployment_failure
from intelligence.incidents import EvidenceEvent, EvidenceKind, analyze_incident
from product.l2_proposals import (
    ALLOW_LISTED_RUNBOOKS,
    REQUIRES_HUMAN,
    L2Proposal,
    build_proposals,
    proposals_to_dicts,
)
from remediation.catalog import default_catalog  # test-only: proves the copied ids have not drifted

BASE = datetime(2026, 8, 22, 10, 0, tzinfo=timezone.utc)


def event(identifier, kind, minutes, summary, severity=4, attributes=()):
    return EvidenceEvent(
        identifier,
        kind,
        "payments",
        BASE + timedelta(minutes=minutes),
        summary,
        "test",
        severity,
        tuple(attributes),
    )


def test_allow_listed_runbook_ids_still_exist_in_the_remediation_catalog():
    """The ids in l2_proposals are copied from remediation/catalog.py; catch drift here."""
    catalog = default_catalog()
    for failure_class, entry in ALLOW_LISTED_RUNBOOKS.items():
        runbook = catalog.get(entry.runbook_id)
        assert runbook.failure_class == failure_class
        assert runbook.reversible is True
        assert entry.rollback_runbook_id == runbook.rollback_id


def test_last_good_deployment_correlation_proposes_a_revert_pr_naming_the_commit_range():
    analysis = analyze_incident(
        [
            event("d0", EvidenceKind.DEPLOYMENT, -60, "release v1", 1, (("commit", "aaa1111"),)),
            event("d1", EvidenceKind.DEPLOYMENT, 0, "release v2", 1, (("commit", "bbb2222"),)),
            event("a1", EvidenceKind.ALERT, 3, "error rate spiked"),
        ],
        service="payments",
    )

    proposals = build_proposals(analysis, service="payments", environment="prod")

    revert = next(p for p in proposals if p.kind == "corrective-pr")
    assert "aaa1111..bbb2222" in revert.exact_action
    assert revert.rollback_path
    assert "d1" in revert.evidence_refs


def test_last_good_commit_attribute_is_enough_for_a_revert_proposal():
    analysis = analyze_incident(
        [
            event(
                "d1",
                EvidenceKind.DEPLOYMENT,
                0,
                "release v2",
                1,
                (("commit", "bbb2222"), ("last_good_commit", "aaa1111")),
            ),
            event("a1", EvidenceKind.ALERT, 3, "error rate spiked"),
        ],
        service="payments",
    )

    proposals = build_proposals(analysis, service="payments", environment="prod")

    assert any(p.kind == "corrective-pr" and "aaa1111..bbb2222" in p.exact_action for p in proposals)


def test_known_failure_class_proposes_an_allow_listed_runbook():
    analysis = analyze_incident(
        [
            event("d1", EvidenceKind.DEPLOYMENT, 0, "release v2", 1),
            event("k1", EvidenceKind.K8S_EVENT, 1, "CrashLoopBackOff for container api"),
        ],
        service="payments",
    )

    proposals = build_proposals(analysis, service="payments", environment="prod")

    runbook = next(p for p in proposals if p.kind == "runbook")
    assert "aks.restart.crashloop" in runbook.exact_action
    assert ALLOW_LISTED_RUNBOOKS["crashloop"].runbook_id == "aks.restart.crashloop"
    assert runbook.rollback_path


def test_readiness_regression_selects_the_rollback_runbook():
    analysis = analyze_incident(
        [
            event("d1", EvidenceKind.DEPLOYMENT, 0, "release v2", 1),
            event("a1", EvidenceKind.ALERT, 2, "readiness probe failed"),
        ],
        service="payments",
    )

    proposals = build_proposals(analysis, service="payments", environment="prod")

    assert any("aks.rollback.readiness" in p.exact_action for p in proposals if p.kind == "runbook")


def test_unrecognized_failure_falls_back_to_a_ticket():
    analysis = analyze_incident(
        [event("a1", EvidenceKind.ALERT, 0, "unexplained latency on the checkout path")],
        service="payments",
    )

    proposals = build_proposals(analysis, service="payments", environment="prod")

    assert [p.kind for p in proposals] == ["ticket"]
    assert "payments" in proposals[0].title
    assert proposals[0].rollback_path


def test_deployment_failure_analysis_produces_the_same_proposal_shape():
    events = [
        event("d0", EvidenceKind.DEPLOYMENT, -60, "release v1", 1, (("commit", "aaa1111"),)),
        event("ado:Platform:7:42", EvidenceKind.DEPLOYMENT, 0, "release v2", 1, (("commit", "bbb2222"),)),
        event("a1", EvidenceKind.ALERT, 4, "readiness probe failed"),
    ]
    analysis = investigate_deployment_failure(
        events, deployment_id="ado:Platform:7:42", service="payments"
    )

    proposals = build_proposals(analysis, service="payments", environment="prod", evidence=events)

    kinds = {p.kind for p in proposals}
    assert "corrective-pr" in kinds
    assert "runbook" in kinds


def test_every_proposal_requires_a_human_and_the_flag_cannot_be_overridden():
    analysis = analyze_incident(
        [event("a1", EvidenceKind.ALERT, 0, "unexplained latency")], service="payments"
    )
    proposals = build_proposals(analysis, service="payments", environment="prod")

    assert REQUIRES_HUMAN is True
    assert all(p.requires_human is True for p in proposals)
    assert all(d["requires_human"] is True for d in proposals_to_dicts(proposals))
    with pytest.raises(TypeError):
        L2Proposal(
            kind="ticket",
            title="t",
            exact_action="a",
            rollback_path="r",
            evidence_refs=(),
            requires_human=False,
        )
