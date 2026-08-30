import hashlib
import hmac
import json

from fastapi.testclient import TestClient

from app.application import create_app
from app.settings import ApplicationSettings
from control_plane.workflows import ControlPlaneWorkflows
from integrations.github.pr_guardian import ChangedFile
from integrations.github.webhook import verify_webhook_signature
from product.pr_guardian_service import PRGuardianService
from intelligence.extractors import ServiceMetadata, build_graph
from state.audit import SqliteAuditLog
from state.store import SqliteStateStore
from telemetry.events import InMemoryTelemetrySink


class FakeGitHub:
    def __init__(self, files):
        self.files = files
        self.checks = []
        self.comments = []

    def list_changed_files(self, repository, pr_number):
        return self.files

    def publish_check(self, *, repository, head_sha, name, conclusion, title, summary):
        self.checks.append({"head_sha": head_sha, "conclusion": conclusion, "summary": summary})

    def publish_comment(self, *, repository, pr_number, body):
        self.comments.append(body)


def make_guardian(tmp_path, files):
    graph = build_graph([
        ServiceMetadata(service="api", owner="platform", tier=1, dependencies=("auth",)),
        ServiceMetadata(service="auth", owner="identity", tier=1),
    ])
    workflows = ControlPlaneWorkflows(
        SqliteStateStore(tmp_path / "state.db"),
        SqliteAuditLog(tmp_path / "audit.db"),
    )
    github = FakeGitHub(files)
    telemetry = InMemoryTelemetrySink()
    return PRGuardianService(graph=graph, github=github, workflows=workflows, telemetry=telemetry), github, telemetry


def payload(action="opened", number=9):
    return {
        "action": action,
        "number": number,
        "repository": {"full_name": "acme/platform"},
        "pull_request": {"head": {"sha": "ff00"}},
    }


def signed_headers(body: bytes, secret: str) -> dict:
    return {
        "X-Hub-Signature-256": "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest(),
        "X-GitHub-Event": "pull_request",
        "X-GitHub-Delivery": "d-42",
        "Content-Type": "application/json",
    }


def webhook_app(secret: str = "hooksecret"):
    return create_app(ApplicationSettings.from_mapping({"EIP_GITHUB_WEBHOOK_SECRET": secret}))


def test_signature_verification_fails_closed():
    secret, body = "s3cret", b"{}"
    sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    assert verify_webhook_signature(secret=secret, body=body, signature_header=sig)
    assert not verify_webhook_signature(secret=secret, body=body, signature_header="sha256=deadbeef")
    assert not verify_webhook_signature(secret=secret, body=body, signature_header=None)
    assert not verify_webhook_signature(secret="", body=body, signature_header=sig)
    assert not verify_webhook_signature(secret=secret, body=body, signature_header="sha1=abc")


def test_webhook_rejects_bad_signature():
    client = TestClient(webhook_app())
    body = json.dumps(payload()).encode()
    response = client.post(
        "/v1/events/github",
        content=body,
        headers={"X-Hub-Signature-256": "sha256=wrong", "X-GitHub-Event": "pull_request"},
    )
    assert response.status_code == 401


def test_webhook_reviews_pull_request_and_emits_telemetry(tmp_path):
    guardian, github, telemetry = make_guardian(
        tmp_path, [ChangedFile(filename="infra/terraform/identity.tf", status="modified")]
    )
    application = webhook_app()
    application.state.pr_guardian = guardian
    try:
        client = TestClient(application)
        body = json.dumps(payload()).encode()
        response = client.post("/v1/events/github", content=body, headers=signed_headers(body, "hooksecret"))
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "reviewed"
        assert data["workflow_id"] == "pr:acme/platform:9"
        assert data["correlation_id"] == "d-42"
        assert github.checks[0]["head_sha"] == "ff00"
        assert telemetry.events[0].operation == "pr-guardian-review"
        assert telemetry.events[0].correlation_id == "d-42"
        assert telemetry.events[0].attributes["score"] == str(data["score"])
    finally:
        application.state.pr_guardian = None


def test_webhook_ignores_non_review_actions():
    client = TestClient(webhook_app())
    body = json.dumps(payload(action="labeled")).encode()
    response = client.post("/v1/events/github", content=body, headers=signed_headers(body, "hooksecret"))
    assert response.status_code == 200
    assert response.json()["status"] == "ignored"


def test_webhook_503_when_guardian_not_configured():
    application = webhook_app()
    application.state.pr_guardian = None
    client = TestClient(application)
    body = json.dumps(payload()).encode()
    response = client.post("/v1/events/github", content=body, headers=signed_headers(body, "hooksecret"))
    assert response.status_code == 503


def test_webhook_ping():
    client = TestClient(webhook_app())
    body = b"{}"
    headers = signed_headers(body, "hooksecret")
    headers["X-GitHub-Event"] = "ping"
    response = client.post("/v1/events/github", content=body, headers=headers)
    assert response.json() == {"status": "pong"}
