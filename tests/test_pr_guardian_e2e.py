import hashlib
import hmac
import json

from fastapi.testclient import TestClient

from app.main import app
from control_plane.workflows import ControlPlaneWorkflows
from intelligence.extractors import ServiceMetadata, build_graph
from sdlc.github_checks import CheckRun, InMemoryCheckPublisher, conclusion_for
from sdlc.github_events import (
    ChangedFile,
    parse_pull_request_event,
    verify_webhook_signature,
)
from sdlc.pr_guardian_service import PRGuardianService
from sdlc.pr_guardian_service import tests_present as detect_tests
from state.audit import SqliteAuditLog
from state.store import SqliteStateStore
from telemetry.events import InMemoryTelemetrySink


def make_service(tmp_path, changed, metadata=None):
    workflows = ControlPlaneWorkflows(
        SqliteStateStore(tmp_path / "state.db"),
        SqliteAuditLog(tmp_path / "audit.db"),
    )
    graph = build_graph(metadata or [
        ServiceMetadata(service="api", owner="platform", tier=1, dependencies=("auth", "database")),
        ServiceMetadata(service="auth", owner="identity", tier=1),
    ])

    class Diff:
        def changed_files(self, repository, pr_number):
            return changed

    publisher = InMemoryCheckPublisher()
    telemetry = InMemoryTelemetrySink()
    service = PRGuardianService(
        diff_provider=Diff(),
        graph_provider=lambda repo: graph,
        workflows=workflows,
        check_publisher=publisher,
        telemetry=telemetry,
    )
    return service, workflows, publisher, telemetry


def make_event(**overrides):
    payload = {
        "action": "opened",
        "repository": {"full_name": "acme/platform"},
        "pull_request": {
            "number": 7,
            "title": "change auth",
            "user": {"login": "dev"},
            "head": {"sha": "abc123", "ref": "feature"},
            "base": {"ref": "main"},
        },
    }
    payload.update(overrides)
    return parse_pull_request_event(payload, delivery_id="d-1")


def test_webhook_signature_round_trip():
    secret, body = "s3cret", b'{"zen": "ok"}'
    sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    assert verify_webhook_signature(secret=secret, body=body, signature_header=sig)
    assert not verify_webhook_signature(secret=secret, body=body, signature_header="sha256=deadbeef")
    assert not verify_webhook_signature(secret=secret, body=body, signature_header=None)
    assert not verify_webhook_signature(secret="", body=body, signature_header=sig)


def test_ignored_actions_do_not_trigger_review():
    assert parse_pull_request_event({"action": "labeled"}) is None
    assert make_event(action="synchronize") is not None


def test_high_risk_pr_produces_action_required_and_audit_chain(tmp_path):
    changed = [
        ChangedFile(path="services/auth/rbac_policy.py"),
        ChangedFile(path="infra/terraform/identity.tf"),
    ] + [ChangedFile(path=f"services/auth/mod_{i}.py") for i in range(30)]
    service, workflows, publisher, telemetry = make_service(tmp_path, changed)

    result = service.handle(make_event())

    assert result.assessment.score >= 70
    assert result.policy.require_additional_approval
    assert publisher.published[0].conclusion in {"neutral", "action_required"}
    assert "security-boundary-change" in publisher.published[0].summary
    workflow = workflows.store.get_workflow("pr:acme/platform:7")
    assert workflow is not None and workflow.plan_hash is not None
    assert workflows.audit.verify_chain()
    assert telemetry.events[0].operation == "pr-guardian-review"


def test_low_risk_pr_with_tests_is_success(tmp_path):
    changed = [
        ChangedFile(path="services/api/handlers.py"),
        ChangedFile(path="tests/test_handlers.py"),
    ]
    service, _, publisher, _ = make_service(tmp_path, changed)
    result = service.handle(make_event())
    assert result.check.conclusion == "success"
    assert not result.policy.block_merge
    assert publisher.published[0].head_sha == "abc123"


def test_redelivery_bumps_workflow_version_only(tmp_path):
    changed = [ChangedFile(path="services/api/handlers.py")]
    service, workflows, publisher, _ = make_service(tmp_path, changed)
    service.handle(make_event())
    service.handle(make_event())
    workflow = workflows.store.get_workflow("pr:acme/platform:7")
    assert workflow.version == 2
    assert len(publisher.published) == 2
    assert workflows.audit.verify_chain()


def test_tests_present_detection():
    assert detect_tests(["tests/test_api.py"])
    assert detect_tests(["pkg/handlers_test.py"])
    assert not detect_tests(["services/api/handlers.py", "README.md"])


def test_conclusion_mapping():
    from intelligence.pr_guardian import PRPolicyDecision

    assert conclusion_for(PRPolicyDecision(False, False, False)) == "success"
    assert conclusion_for(PRPolicyDecision(True, False, False)) == "neutral"
    assert conclusion_for(PRPolicyDecision(True, True, True)) == "action_required"


def signed(body: bytes, secret: str) -> dict:
    return {
        "X-Hub-Signature-256": "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest(),
        "X-GitHub-Event": "pull_request",
        "X-GitHub-Delivery": "d-42",
        "Content-Type": "application/json",
    }


def test_webhook_endpoint_rejects_bad_signature(monkeypatch):
    monkeypatch.setenv("EIP_GITHUB_WEBHOOK_SECRET", "hooksecret")
    client = TestClient(app)
    body = json.dumps({"action": "opened"}).encode()
    response = client.post(
        "/v1/events/github",
        content=body,
        headers={"X-Hub-Signature-256": "sha256=wrong", "X-GitHub-Event": "pull_request"},
    )
    assert response.status_code == 401


def test_webhook_endpoint_reviews_pull_request(monkeypatch, tmp_path):
    monkeypatch.setenv("EIP_GITHUB_WEBHOOK_SECRET", "hooksecret")
    changed = [ChangedFile(path="infra/terraform/identity.tf")]
    service, _, publisher, _ = make_service(tmp_path, changed)
    app.state.pr_guardian = service
    try:
        client = TestClient(app)
        payload = {
            "action": "opened",
            "repository": {"full_name": "acme/platform"},
            "pull_request": {
                "number": 9,
                "title": "iac change",
                "user": {"login": "dev"},
                "head": {"sha": "ff00", "ref": "feature"},
                "base": {"ref": "main"},
            },
        }
        body = json.dumps(payload).encode()
        response = client.post("/v1/events/github", content=body, headers=signed(body, "hooksecret"))
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "reviewed"
        assert data["workflow_id"] == "pr:acme/platform:9"
        assert publisher.published[0].head_sha == "ff00"
    finally:
        app.state.pr_guardian = None


def test_webhook_endpoint_503_when_unconfigured(monkeypatch):
    monkeypatch.setenv("EIP_GITHUB_WEBHOOK_SECRET", "hooksecret")
    app.state.pr_guardian = None
    client = TestClient(app)
    payload = {
        "action": "opened",
        "repository": {"full_name": "acme/platform"},
        "pull_request": {
            "number": 1,
            "title": "x",
            "user": {"login": "dev"},
            "head": {"sha": "aa", "ref": "f"},
            "base": {"ref": "main"},
        },
    }
    body = json.dumps(payload).encode()
    response = client.post("/v1/events/github", content=body, headers=signed(body, "hooksecret"))
    assert response.status_code == 503
