"""The operational-intelligence triggers: a real webhook path into L1 analysis and L2 proposals."""
import json

import pytest
from fastapi.testclient import TestClient

from app.main import app
from operations_fixtures import ADO_FAILED_RUN, COMMON_ALERT, write_evidence_fixture

SECRET = "operations-shared-secret"


@pytest.fixture(autouse=True)
def _clean_operations_state():
    if hasattr(app.state, "operations"):
        del app.state.operations
    yield
    if hasattr(app.state, "operations"):
        del app.state.operations


@pytest.fixture
def configured_env(monkeypatch, tmp_path):
    fixture = write_evidence_fixture(tmp_path)
    monkeypatch.setenv("EIP_OPERATIONS_WEBHOOK_SECRET", SECRET)
    monkeypatch.setenv("EIP_OPERATIONS_EVIDENCE", f"fixture:{fixture}")
    monkeypatch.setenv("EIP_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.delenv("EIP_PR_GUARDIAN_WEBHOOK", raising=False)
    monkeypatch.delenv("EIP_FEEDBACK_DB", raising=False)
    return fixture


def _unconfigure(monkeypatch):
    for name in ("EIP_OPERATIONS_WEBHOOK_SECRET", "EIP_OPERATIONS_EVIDENCE"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.delenv("EIP_PR_GUARDIAN_WEBHOOK", raising=False)
    monkeypatch.delenv("EIP_FEEDBACK_DB", raising=False)


@pytest.mark.parametrize(
    "route,payload",
    [("/v1/events/deployment", ADO_FAILED_RUN), ("/v1/events/incident", COMMON_ALERT)],
)
def test_routes_answer_503_when_the_capability_is_unconfigured(monkeypatch, route, payload):
    _unconfigure(monkeypatch)
    with TestClient(app) as client:
        response = client.post(route, json=payload, headers={"X-EIP-Operations-Secret": SECRET})
    assert response.status_code == 503
    assert "not configured" in response.json()["detail"]


@pytest.mark.parametrize(
    "route,payload",
    [("/v1/events/deployment", ADO_FAILED_RUN), ("/v1/events/incident", COMMON_ALERT)],
)
def test_routes_answer_401_on_a_wrong_or_missing_secret(configured_env, route, payload):
    with TestClient(app) as client:
        wrong = client.post(route, json=payload, headers={"X-EIP-Operations-Secret": "nope"})
        absent = client.post(route, json=payload)
    assert wrong.status_code == 401
    assert absent.status_code == 401


def test_deployment_route_returns_analysis_and_l2_proposals(configured_env):
    with TestClient(app) as client:
        assert client.get("/healthz").json()["capabilities"]["operations"] == "configured"
        response = client.post(
            "/v1/events/deployment",
            json=ADO_FAILED_RUN,
            headers={"X-EIP-Operations-Secret": SECRET},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "investigated"
    assert body["correlation_id"]
    assert body["workflow_id"] == "deployment-failure:ado:Platform:7:42"
    assert body["analysis"]["deployment_id"] == "ado:Platform:7:42"
    assert body["analysis"]["hypotheses"]
    kinds = {p["kind"] for p in body["proposals"]}
    assert kinds & {"corrective-pr", "runbook", "ticket"}
    assert all(p["requires_human"] is True for p in body["proposals"])
    # The revert range is anchored on the deployment the hook reported, not on the
    # hotfix that was deployed afterwards and is also inside the evidence window.
    assert any("aaa1111..bbb2222" in p["exact_action"] for p in body["proposals"])
    assert all("ccc3333" not in json.dumps(p) for p in body["proposals"])


def test_incident_route_returns_analysis_blast_radius_and_l2_proposals(configured_env):
    with TestClient(app) as client:
        response = client.post(
            "/v1/events/incident",
            json=COMMON_ALERT,
            headers={"X-EIP-Operations-Secret": SECRET},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["workflow_id"] == "incident:INC-42"
    assert body["service"] == "payments"
    assert body["impacted_services"] == ["payments"]
    assert body["analysis"]["hypotheses"]
    assert body["proposals"]
    assert all(p["requires_human"] is True for p in body["proposals"])


def test_resolved_alerts_are_ignored_rather_than_investigated(configured_env):
    payload = {
        "schemaId": "azureMonitorCommonAlertSchema",
        "data": {
            "essentials": dict(COMMON_ALERT["data"]["essentials"], monitorCondition="Resolved"),
            "customProperties": {"service": "payments", "environment": "prod"},
        },
    }
    with TestClient(app) as client:
        response = client.post(
            "/v1/events/incident", json=payload, headers={"X-EIP-Operations-Secret": SECRET}
        )
    assert response.status_code == 200
    assert response.json() == {"status": "ignored", "reason": "monitorCondition is not Fired"}


@pytest.mark.parametrize(
    "route,payload",
    [("/v1/events/deployment", {"resource": {}}), ("/v1/events/incident", {"data": {}})],
)
def test_unparseable_payloads_are_rejected_with_400(configured_env, route, payload):
    with TestClient(app) as client:
        response = client.post(
            route, json=payload, headers={"X-EIP-Operations-Secret": SECRET}
        )
    assert response.status_code == 400


def test_the_api_never_executes_a_proposal(configured_env):
    """L2 stops at a proposal; the response is the whole delivery mechanism."""
    with TestClient(app) as client:
        body = client.post(
            "/v1/events/deployment",
            json=ADO_FAILED_RUN,
            headers={"X-EIP-Operations-Secret": SECRET},
        ).json()
    assert body["autonomy_level"] == "L2-propose"
    assert body["executed"] is False


def test_enabling_operations_without_its_dependencies_fails_closed_at_startup(monkeypatch):
    monkeypatch.setenv("EIP_OPERATIONS_WEBHOOK_SECRET", SECRET)
    monkeypatch.delenv("EIP_OPERATIONS_EVIDENCE", raising=False)
    monkeypatch.delenv("EIP_STATE_DIR", raising=False)
    monkeypatch.delenv("EIP_PR_GUARDIAN_WEBHOOK", raising=False)
    monkeypatch.delenv("EIP_FEEDBACK_DB", raising=False)

    with pytest.raises(RuntimeError) as excinfo:
        with TestClient(app):
            pass

    message = str(excinfo.value)
    assert "EIP_OPERATIONS_EVIDENCE" in message
    assert "EIP_STATE_DIR" in message


def test_azure_monitor_evidence_mode_lists_every_missing_azure_variable(monkeypatch, tmp_path):
    monkeypatch.setenv("EIP_OPERATIONS_WEBHOOK_SECRET", SECRET)
    monkeypatch.setenv("EIP_OPERATIONS_EVIDENCE", "azure-monitor")
    monkeypatch.setenv("EIP_STATE_DIR", str(tmp_path / "state"))
    for name in ("AZURE_TENANT_ID", "AZURE_CLIENT_ID", "EIP_OPERATIONS_LOG_ANALYTICS_WORKSPACE_ID"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.delenv("EIP_PR_GUARDIAN_WEBHOOK", raising=False)
    monkeypatch.delenv("EIP_FEEDBACK_DB", raising=False)

    with pytest.raises(RuntimeError) as excinfo:
        with TestClient(app):
            pass

    message = str(excinfo.value)
    for name in ("AZURE_TENANT_ID", "AZURE_CLIENT_ID", "EIP_OPERATIONS_LOG_ANALYTICS_WORKSPACE_ID"):
        assert name in message


def test_an_unknown_evidence_mode_is_refused_at_startup(monkeypatch, tmp_path):
    monkeypatch.setenv("EIP_OPERATIONS_WEBHOOK_SECRET", SECRET)
    monkeypatch.setenv("EIP_OPERATIONS_EVIDENCE", "guesswork")
    monkeypatch.setenv("EIP_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.delenv("EIP_PR_GUARDIAN_WEBHOOK", raising=False)
    monkeypatch.delenv("EIP_FEEDBACK_DB", raising=False)

    with pytest.raises(RuntimeError, match="EIP_OPERATIONS_EVIDENCE"):
        with TestClient(app):
            pass


def test_a_fixture_evidence_path_that_does_not_exist_fails_closed(monkeypatch, tmp_path):
    monkeypatch.setenv("EIP_OPERATIONS_WEBHOOK_SECRET", SECRET)
    monkeypatch.setenv("EIP_OPERATIONS_EVIDENCE", f"fixture:{tmp_path / 'absent.json'}")
    monkeypatch.setenv("EIP_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.delenv("EIP_PR_GUARDIAN_WEBHOOK", raising=False)
    monkeypatch.delenv("EIP_FEEDBACK_DB", raising=False)

    with pytest.raises(RuntimeError, match="absent.json"):
        with TestClient(app):
            pass
