"""Focused contracts for the PR Guardian pipeline components.

The end-to-end tests continue to protect the public service. These tests make
the extracted stages independently reviewable, so future changes do not need
to reintroduce collection, publishing, and telemetry into the facade.
"""

from __future__ import annotations

from integrations.github.pr_guardian import ChangedFile, PullRequestEvent
from intelligence.graph import ServiceGraph, ServiceNode
from intelligence.pr_guardian import PRPolicyDecision
from intelligence.risk import RiskAssessment, RiskFactor
from product.pr_guardian.finding_factory import PRFindingFactory
from product.pr_guardian.enforcement import EnforcementDecision
from product.pr_guardian.publication import PRGuardianPublisher
from product.pr_guardian.review_pipeline import PRReviewPreparer
from product.pr_guardian.telemetry import PRGuardianTelemetryRecorder
from telemetry.events import InMemoryTelemetrySink


class GitHub:
    def __init__(self) -> None:
        self.checks: list[dict[str, object]] = []
        self.comments: list[dict[str, object]] = []

    def list_changed_files(self, repository: str, pr_number: int) -> list[ChangedFile]:
        return [
            ChangedFile("services/payments/auth.py", "modified", 10, 1),
            ChangedFile("infra/payments/rbac.tf", "modified", 4, 0),
        ]

    def publish_check(self, **kwargs: object) -> None:
        self.checks.append(kwargs)

    def publish_comment(self, **kwargs: object) -> None:
        self.comments.append(kwargs)


class History:
    def similar_failed_changes(self, *, repository: str, filenames: tuple[str, ...]) -> int:
        assert repository == "acme/platform"
        assert filenames == ("services/payments/auth.py", "infra/payments/rbac.tf")
        return 1


def graph() -> ServiceGraph:
    value = ServiceGraph()
    value.add(ServiceNode(name="payments", tier=1, dependencies=("identity",)))
    value.add(ServiceNode(name="identity", tier=1))
    return value


def event() -> PullRequestEvent:
    return PullRequestEvent("acme/platform", 7, "deadbeef", "opened")


def assessment() -> RiskAssessment:
    return RiskAssessment(
        score=12,
        band="low",
        blast_radius=(),
        factors=(RiskFactor("infrastructure-change", 12, "IaC changed"),),
    )


def test_preparer_collects_and_scores_without_publishing_or_recording():
    github = GitHub()

    prepared = PRReviewPreparer(
        graph=graph(), github=github, history=History()
    ).prepare(event())

    assert prepared.changed_services == ("payments",)
    assert prepared.primary_service == "payments"
    assert prepared.filenames == ("services/payments/auth.py", "infra/payments/rbac.tf")
    assert {factor.name for factor in prepared.assessment.factors} >= {
        "critical-service",
        "infrastructure-change",
        "weak-test-evidence",
        "historical-regression",
    }
    assert prepared.simulated_policy == PRPolicyDecision(True, True, False)
    assert github.checks == []
    assert github.comments == []


def test_publisher_renders_a_precomputed_decision_without_deciding_it():
    github = GitHub()

    PRGuardianPublisher(github).publish(
        event=event(),
        assessment=assessment(),
        workflow_id="pr:acme/platform:7",
        changed_services=(),
        policy=PRPolicyDecision(False, False, False),
        mode="shadow",
        conclusion="neutral",
        enforcement=EnforcementDecision(False, "mode-not-enforcing"),
        company_context=None,
    )

    assert github.checks[0]["conclusion"] == "neutral"
    assert github.checks[0]["title"] == "Shadow risk: 12/100 (low)"
    assert "shadow observation" in str(github.comments[0]["body"])


def test_telemetry_recorder_owns_the_stable_review_event_shape():
    finding = PRFindingFactory(policy_version="pr-policy-v1").create(
        event=event(),
        assessment=assessment(),
        policy=PRPolicyDecision(False, False, False),
        correlation_id="corr-7",
        company_context=None,
    )
    sink = InMemoryTelemetrySink()

    PRGuardianTelemetryRecorder(sink).record(
        event=event(),
        assessment=assessment(),
        finding=finding,
        primary_service="payments",
        company_context=None,
        conclusion="neutral",
        latency_ms=2.5,
    )

    assert sink.events[0].correlation_id == "corr-7"
    assert sink.events[0].operation == "pr-guardian-review"
    assert sink.events[0].attributes == {
        "pr": "7",
        "head_sha": "deadbeef",
        "score": "12",
        "band": "low",
        "company_brain_context": "unqualified",
        "context_version": "legacy-graph:v1",
    }
