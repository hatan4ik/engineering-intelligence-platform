import hashlib
import hmac
import json

import pytest
from fastapi.testclient import TestClient

from app.main import app
from feedback.store import SqliteFeedbackStore


WIRED_ATTRIBUTES = (
    "pr_guardian",
    "feedback_recorder",
    "service_intelligence_provider",
    "portfolio_intelligence_provider",
    "portfolio_trend_provider",
)


@pytest.fixture(autouse=True)
def _clean_app_state():
    for name in WIRED_ATTRIBUTES:
        if hasattr(app.state, name):
            delattr(app.state, name)
    yield
    for name in WIRED_ATTRIBUTES:
        if hasattr(app.state, name):
            delattr(app.state, name)


def _signed(body: bytes, secret: str) -> dict[str, str]:
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return {
        "x-hub-signature-256": f"sha256={digest}",
        "x-github-event": "pull_request",
        "content-type": "application/json",
    }


def _closed_pr_payload() -> dict[str, object]:
    return {
        "action": "closed",
        "number": 9,
        "repository": {"full_name": "acme/platform"},
        "pull_request": {
            "number": 9,
            "merged": True,
            "head": {"sha": "ff00"},
            "base": {"ref": "main"},
        },
    }


def test_healthz_reports_every_capability_as_unconfigured_by_default(monkeypatch):
    monkeypatch.delenv("EIP_BACKEND", raising=False)
    response = TestClient(app).get("/healthz")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "capabilities": {
            "query": "deterministic",
            "pr_guardian_webhook": "unconfigured",
            "feedback_recorder": "unconfigured",
            "portal": "unconfigured",
        },
    }


def test_lifespan_wires_feedback_recorder_from_environment(monkeypatch, tmp_path):
    db = tmp_path / "feedback.db"
    monkeypatch.setenv("EIP_FEEDBACK_DB", str(db))
    monkeypatch.setenv("EIP_GITHUB_WEBHOOK_SECRET", "hooksecret")
    monkeypatch.delenv("EIP_PR_GUARDIAN_WEBHOOK", raising=False)

    with TestClient(app) as client:
        assert client.get("/healthz").json()["capabilities"]["feedback_recorder"] == "sqlite"
        body = json.dumps(_closed_pr_payload()).encode()
        response = client.post("/v1/events/github", content=body, headers=_signed(body, "hooksecret"))
        assert response.status_code == 200
        assert response.json() == {"status": "outcome-recorded", "merged": True}

    events = SqliteFeedbackStore(db).events()
    assert len(events) == 1
    assert events[0].capability == "pr-guardian"

    # Shutdown removes what startup configured so the process is not left half-wired.
    assert not hasattr(app.state, "feedback_recorder")


def test_lifespan_wires_shadow_pr_guardian_when_explicitly_enabled(monkeypatch, tmp_path):
    graph_root = tmp_path / "checkout"
    graph_root.mkdir()
    monkeypatch.setenv("EIP_PR_GUARDIAN_WEBHOOK", "enabled")
    monkeypatch.setenv("GITHUB_TOKEN", "token")
    monkeypatch.setenv("EIP_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("EIP_SERVICE_GRAPH_ROOT", str(graph_root))
    monkeypatch.delenv("EIP_FEEDBACK_DB", raising=False)

    with TestClient(app) as client:
        capabilities = client.get("/healthz").json()["capabilities"]
        assert capabilities["pr_guardian_webhook"] == "shadow"
        assert app.state.pr_guardian.mode == "shadow"

    assert not hasattr(app.state, "pr_guardian")


def test_enabling_pr_guardian_webhook_without_its_dependencies_fails_closed_at_startup(monkeypatch):
    monkeypatch.setenv("EIP_PR_GUARDIAN_WEBHOOK", "enabled")
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("EIP_STATE_DIR", raising=False)
    monkeypatch.delenv("EIP_SERVICE_GRAPH_ROOT", raising=False)

    with pytest.raises(RuntimeError, match="GITHUB_TOKEN"):
        with TestClient(app):
            pass
