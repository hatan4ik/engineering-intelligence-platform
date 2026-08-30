"""Contract tests for bounded failure behavior at runtime dependency edges."""

from __future__ import annotations

import hashlib
import hmac
import urllib.error
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.application import create_app
from app.operations.capability import OperationsCapability
from app.settings import ApplicationSettings
from integrations.azure.monitor import AzureMonitorEvidenceClient, AzureMonitorQuery
from integrations.azure.resource_graph import AzureResourceGraphClient
from integrations.github.pr_guardian import GitHubAPIError, GitHubRestPRClient
from remediation.catalog import AutonomyLevel, default_catalog
from remediation.opa_policy import OpaPolicyClient, PolicyControlState
from remediation.policy import ActionRequest, ServiceAutonomy
from resilience.dependencies import DependencyBoundary, DependencyLimits, DependencyUnavailable
from operations_fixtures import ADO_FAILED_RUN, write_evidence_fixture


class _Clock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


class _Token:
    token = "test-token"


class _Credential:
    def get_token(self, *scopes: str) -> _Token:
        return _Token()


def _single_failure_boundary(name: str) -> DependencyBoundary:
    return DependencyBoundary(
        name,
        DependencyLimits(max_in_flight=2, failure_threshold=1, recovery_seconds=30),
        clock=_Clock(),
    )


def _raise_url_error(*args: object, **kwargs: object) -> None:
    raise urllib.error.URLError("dependency down")


def test_github_client_stops_repeated_transient_requests_after_the_breaker_opens(monkeypatch):
    calls = 0

    def unavailable(*args: object, **kwargs: object) -> None:
        nonlocal calls
        calls += 1
        _raise_url_error(*args, **kwargs)

    monkeypatch.setattr("integrations.github.pr_guardian.urllib.request.urlopen", unavailable)
    client = GitHubRestPRClient(
        "token",
        dependency=_single_failure_boundary("github-rest"),
    )

    with pytest.raises(GitHubAPIError) as first:
        client.list_changed_files("acme/company-brain", 42)
    with pytest.raises(GitHubAPIError, match="circuit is open") as second:
        client.list_changed_files("acme/company-brain", 42)

    assert first.value.status == 503
    assert second.value.status == 503
    assert calls == 1


def test_opa_fails_closed_and_stops_repeated_transient_policy_requests(monkeypatch):
    calls = 0

    def unavailable(*args: object, **kwargs: object) -> None:
        nonlocal calls
        calls += 1
        _raise_url_error(*args, **kwargs)

    monkeypatch.setattr("remediation.opa_policy.urllib.request.urlopen", unavailable)
    client = OpaPolicyClient(
        "http://opa.invalid",
        dependency=_single_failure_boundary("opa-remediation-policy"),
    )
    policy = ServiceAutonomy(
        "payments",
        "prod",
        AutonomyLevel.APPROVE_AND_EXECUTE,
        ("aks.rollout.undo",),
        5,
    )
    request = ActionRequest("payments", "prod", "aks.rollout.undo", 2)
    arguments = {
        "runbook": default_catalog().get("aks.rollout.undo"),
        "policy": policy,
        "request": request,
        "approval_verified": True,
        "control": PolicyControlState(),
    }

    first = client.evaluate(**arguments)
    second = client.evaluate(**arguments)

    assert not first.allowed
    assert not second.allowed
    assert calls == 1


@pytest.mark.parametrize(
    ("client", "invoke", "dependency_name"),
    [
        (
            AzureMonitorEvidenceClient(
                credential=_Credential(),
                dependency=_single_failure_boundary("azure-monitor-logs"),
            ),
            lambda client: client._post(
                AzureMonitorQuery(
                    workspace_id="workspace",
                    service="payments",
                    start=datetime(2026, 8, 30, tzinfo=timezone.utc),
                    end=datetime(2026, 8, 30, 1, tzinfo=timezone.utc),
                    kql="AppTraces | take 1",
                )
            ),
            "azure-monitor-logs",
        ),
        (
            AzureResourceGraphClient(
                subscriptions=("subscription",),
                credential=_Credential(),
                dependency=_single_failure_boundary("azure-resource-graph"),
            ),
            lambda client: client._post("resources | take 1"),
            "azure-resource-graph",
        ),
    ],
)
def test_azure_adapters_fail_fast_once_the_dependency_circuit_is_open(
    monkeypatch,
    client,
    invoke,
    dependency_name,
):
    calls = 0

    def unavailable(*args: object, **kwargs: object) -> None:
        nonlocal calls
        calls += 1
        _raise_url_error(*args, **kwargs)

    monkeypatch.setattr("urllib.request.urlopen", unavailable)

    with pytest.raises(DependencyUnavailable, match=dependency_name):
        invoke(client)
    with pytest.raises(DependencyUnavailable, match="circuit is open"):
        invoke(client)

    assert calls == 1


class _UnavailableGuardian:
    async def evaluate(self, *args: object, **kwargs: object) -> object:
        raise GitHubAPIError("GitHub unavailable", 503)


class _UnavailableInvestigator:
    async def investigate(self, *args: object, **kwargs: object) -> object:
        raise DependencyUnavailable("azure-monitor-logs", "circuit is open")


def _signed_headers(body: bytes, secret: str) -> dict[str, str]:
    return {
        "X-Hub-Signature-256": "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest(),
        "X-GitHub-Event": "pull_request",
        "X-GitHub-Delivery": "delivery-42",
        "Content-Type": "application/json",
    }


def test_webhook_returns_a_retryable_503_when_github_is_unavailable():
    secret = "webhook-secret"
    application = create_app(ApplicationSettings.from_mapping({"EIP_GITHUB_WEBHOOK_SECRET": secret}))
    application.state.pr_guardian = _UnavailableGuardian()
    body = b'{"action":"opened","number":42,"repository":{"full_name":"acme/company-brain"},"pull_request":{"head":{"sha":"abc"}}}'

    with TestClient(application) as client:
        response = client.post("/v1/events/github", content=body, headers=_signed_headers(body, secret))

    assert response.status_code == 503
    assert response.headers["x-correlation-id"] == "delivery-42"
    assert response.json()["detail"] == "PR Guardian cannot reach GitHub; retry the delivery"


def test_operations_webhook_returns_a_retryable_503_when_evidence_is_unavailable(tmp_path):
    secret = "operations-secret"
    fixture = write_evidence_fixture(tmp_path)
    application = create_app(
        ApplicationSettings.from_mapping(
            {
                "EIP_OPERATIONS_WEBHOOK_SECRET": secret,
                "EIP_OPERATIONS_EVIDENCE": f"fixture:{fixture}",
                "EIP_STATE_DIR": str(tmp_path / "state"),
            }
        )
    )
    unavailable = _UnavailableInvestigator()

    with TestClient(application) as client:
        application.state.operations = OperationsCapability(
            evidence_mode="test",
            incident=unavailable,
            deployment=unavailable,
        )
        response = client.post(
            "/v1/events/deployment",
            json=ADO_FAILED_RUN,
            headers={"X-EIP-Operations-Secret": secret, "X-Correlation-Id": "ops-42"},
        )

    assert response.status_code == 503
    assert response.headers["x-correlation-id"] == "ops-42"
    assert response.json()["detail"] == "operational evidence dependency is unavailable; retry the event"
