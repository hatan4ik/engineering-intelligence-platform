from integrations.github.pr_guardian import ChangedFile, PullRequestEvent, normalize_pull_request_event
from intelligence.graph import ServiceGraph, ServiceNode
from product.pr_guardian_service import PRGuardianService
from control_plane.workflows import ControlPlaneWorkflows
from state.audit import SqliteAuditLog
from state.store import SqliteStateStore


class FakeGitHub:
    def __init__(self, files):
        self.files = files
        self.checks = []
        self.comments = []

    def list_changed_files(self, repository, pr_number):
        return list(self.files)

    def publish_check(self, **kwargs):
        self.checks.append(kwargs)

    def publish_comment(self, **kwargs):
        self.comments.append(kwargs)


class History:
    def similar_failed_changes(self, *, repository, filenames):
        return 1


def graph():
    g = ServiceGraph()
    g.add(ServiceNode(name="payments", tier=1, dependencies=("identity",)))
    g.add(ServiceNode(name="identity", tier=1))
    g.add(ServiceNode(name="checkout", tier=2, dependencies=("payments",)))
    return g


def test_normalize_github_pr_payload():
    event = normalize_pull_request_event({
        "action": "synchronize",
        "number": 42,
        "repository": {"full_name": "acme/platform"},
        "pull_request": {"head": {"sha": "abc123"}},
    })
    assert event.repository == "acme/platform"
    assert event.number == 42
    assert event.head_sha == "abc123"


def test_pr_guardian_maps_services_scores_persists_and_publishes(tmp_path):
    github = FakeGitHub([
        ChangedFile("services/payments/auth.py", "modified", 20, 3),
        ChangedFile("infra/payments/rbac.tf", "modified", 10, 1),
    ])
    store = SqliteStateStore(tmp_path / "state.db")
    audit = SqliteAuditLog(tmp_path / "audit.db")
    service = PRGuardianService(
        graph=graph(),
        github=github,
        workflows=ControlPlaneWorkflows(store, audit),
        history=History(),
    )

    result = service.evaluate(PullRequestEvent("acme/platform", 7, "deadbeef", "opened"))

    assert result.changed_services == ("payments",)
    assert result.assessment.score >= 70
    assert result.policy.require_additional_approval is True
    assert store.get_workflow("pr:acme/platform:7") is not None
    assert audit.verify_chain() is True
    assert github.checks[0]["head_sha"] == "deadbeef"
    assert github.checks[0]["name"] == "Engineering Intelligence / PR Guardian"
    assert github.comments and "Risk score" in github.comments[0]["body"]


def test_low_risk_pr_publishes_success(tmp_path):
    github = FakeGitHub([
        ChangedFile("docs/README.md", "modified", 2, 1),
    ])
    service = PRGuardianService(
        graph=graph(),
        github=github,
        workflows=ControlPlaneWorkflows(
            SqliteStateStore(tmp_path / "state.db"),
            SqliteAuditLog(tmp_path / "audit.db"),
        ),
    )
    result = service.evaluate(PullRequestEvent("acme/platform", 8, "cafebabe", "opened"))
    assert result.assessment.score == 0
    assert result.conclusion == "success"
    assert github.checks[0]["conclusion"] == "success"
