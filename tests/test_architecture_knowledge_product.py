from datetime import datetime, timedelta, timezone

from intelligence.architecture_guard import ArchitectureRule
from intelligence.knowledge_decay import KnowledgeRecord
from product.architecture_review import ChangedArtifact, review_architecture
from product.knowledge_maintenance import plan_knowledge_maintenance


def test_architecture_guard_blocks_high_severity_and_renders_provenance():
    rules = (
        ArchitectureRule(
            "ADR-007",
            "infra/**/*.tf",
            ("public_network_access_enabled = true",),
            "ADR-007 requires private data-plane access",
            severity=5,
        ),
    )
    review = review_architecture(
        [ChangedArtifact("infra/app/main.tf", "public_network_access_enabled = true")],
        rules=rules,
    )
    assert review.conclusion == "failure"
    assert review.violations[0].rule_id == "ADR-007"
    assert "ADR-007" in review.summary
    assert "eip-architecture-guard" in review.summary


def test_architecture_guard_is_success_when_no_rules_match():
    review = review_architecture(
        [ChangedArtifact("README.md", "hello")],
        rules=(ArchitectureRule("ADR-X", "infra/*.tf", ("bad",), "no bad"),),
    )
    assert review.conclusion == "success"
    assert review.violations == ()


def test_knowledge_decay_produces_reviewable_actions_not_silent_edits():
    now = datetime.now(timezone.utc)
    plan = plan_knowledge_maintenance([
        KnowledgeRecord("doc:old", "runbook", "Payments Runbook", "1", now - timedelta(days=365), owner=None),
        KnowledgeRecord("adr:a", "adr", "Use Queue", "1", now, owner="platform"),
        KnowledgeRecord("adr:b", "adr", "Use Queue", "2", now, owner="platform"),
    ], stale_after_days=180)
    actions = {(item.source_id, item.action) for item in plan.items}
    assert ("doc:old", "request-owner-review") in actions
    assert ("doc:old", "assign-accountable-owner") in actions
    assert ("adr:a", "resolve-conflicting-active-revisions") in actions
    assert "does not silently rewrite" in plan.summary
