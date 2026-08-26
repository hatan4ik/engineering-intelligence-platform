from datetime import datetime, timedelta, timezone

from integrations.github.intelligence_publishers import (
    ARCHITECTURE_MARKER,
    KNOWLEDGE_MARKER,
    GitHubArchitecturePublisher,
    GitHubKnowledgeMaintenancePublisher,
)
from integrations.github.pr_guardian import GitHubRestPRClient
from intelligence.architecture_guard import ArchitectureRule
from intelligence.knowledge_decay import KnowledgeRecord
from product.architecture_review import ChangedArtifact, review_architecture
from product.knowledge_maintenance import plan_knowledge_maintenance


class Client:
    def __init__(self):
        self.checks = []
        self.comments = []
        self.issues = []

    def publish_check(self, **kwargs):
        self.checks.append(kwargs)

    def publish_sticky_comment(self, **kwargs):
        self.comments.append(kwargs)

    def ensure_maintenance_issue(self, **kwargs):
        self.issues.append(kwargs)
        return 17


def test_architecture_review_publishes_check_and_sticky_comment():
    review = review_architecture(
        [ChangedArtifact("infra/main.tf", "public = true")],
        rules=(ArchitectureRule("ADR-1", "infra/*.tf", ("public = true",), "private only", 5),),
    )
    client = Client()
    GitHubArchitecturePublisher(client, "acme/repo", 42, "abc").publish(review)
    assert client.checks[0]["conclusion"] == "failure"
    assert client.comments[0]["marker"] == ARCHITECTURE_MARKER
    assert "ADR-1" in client.comments[0]["body"]


def test_knowledge_maintenance_creates_or_updates_single_marked_issue():
    now = datetime.now(timezone.utc)
    plan = plan_knowledge_maintenance([
        KnowledgeRecord("runbook:1", "runbook", "Old Runbook", "1", now - timedelta(days=365), owner=None)
    ])
    client = Client()
    issue = GitHubKnowledgeMaintenancePublisher(client, "acme/repo").publish(plan)
    assert issue == 17
    assert client.issues[0]["marker"] == KNOWLEDGE_MARKER
    assert "knowledge-maintenance" in client.issues[0]["labels"]


def test_empty_knowledge_plan_does_not_create_noise():
    client = Client()
    plan = plan_knowledge_maintenance([])
    assert GitHubKnowledgeMaintenancePublisher(client, "acme/repo").publish(plan) is None
    assert client.issues == []


class RecordingRestClient(GitHubRestPRClient):
    def __init__(self, responses):
        super().__init__("token")
        self.responses = list(responses)
        self.calls = []

    def _request(self, method, path, payload=None):
        self.calls.append((method, path, payload))
        return self.responses.pop(0) if self.responses else None


def test_generic_sticky_comment_updates_existing_marker():
    client = RecordingRestClient([
        {"login": "eip-bot"},
        [{"id": 9, "body": "<!-- eip-architecture-guard -->\nold", "user": {"login": "eip-bot"}}],
        None,
    ])
    client.publish_sticky_comment(
        repository="acme/repo", pr_number=3,
        marker=ARCHITECTURE_MARKER, body="new",
    )
    assert client.calls[-1][0] == "PATCH"
    assert client.calls[-1][1].endswith("/issues/comments/9")
    assert ARCHITECTURE_MARKER in client.calls[-1][2]["body"]


def test_maintenance_issue_updates_existing_non_pr_issue():
    client = RecordingRestClient([
        [{"number": 12, "body": f"{KNOWLEDGE_MARKER}\nold"}],
        None,
    ])
    number = client.ensure_maintenance_issue(
        repository="acme/repo", marker=KNOWLEDGE_MARKER,
        title="Knowledge maintenance", body="new", labels=("knowledge-maintenance",),
    )
    assert number == 12
    assert client.calls[-1][0] == "PATCH"
    assert client.calls[-1][1].endswith("/issues/12")
