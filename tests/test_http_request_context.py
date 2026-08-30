from fastapi.testclient import TestClient

from app.application import create_app
from app.settings import ApplicationSettings
from telemetry.trace_context import TraceContext


_PARENT_TRACEPARENT = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"


def test_http_boundary_preserves_correlation_and_creates_a_w3c_child_trace():
    app = create_app(ApplicationSettings.from_mapping({}))

    with TestClient(app) as client:
        response = client.post(
            "/v1/query",
            headers={
                "x-correlation-id": "upstream:request-42",
                "traceparent": _PARENT_TRACEPARENT,
            },
            json={"question": "How should production remediation work?"},
        )

    assert response.status_code == 200
    assert response.json()["correlation_id"] == "upstream:request-42"
    assert response.headers["x-correlation-id"] == "upstream:request-42"
    child = TraceContext.from_headers(response.headers).traceparent
    assert child is not None
    assert child.split("-")[1] == _PARENT_TRACEPARENT.split("-")[1]
    assert child.split("-")[2] != _PARENT_TRACEPARENT.split("-")[2]


def test_github_delivery_is_the_correlation_fallback_when_no_generic_id_exists():
    app = create_app(ApplicationSettings.from_mapping({"EIP_GITHUB_WEBHOOK_SECRET": "hooksecret"}))

    with TestClient(app) as client:
        response = client.post(
            "/v1/events/github",
            content=b"{}",
            headers={
                "x-hub-signature-256": "sha256=wrong",
                "x-github-event": "ping",
                "x-github-delivery": "delivery-42",
            },
        )

    assert response.status_code == 401
    assert response.headers["x-correlation-id"] == "delivery-42"


def test_invalid_correlation_id_is_rejected_before_the_route_or_settings_are_used():
    app = create_app(ApplicationSettings.from_mapping({}))

    response = TestClient(app).get("/healthz", headers={"x-correlation-id": "has a space"})

    assert response.status_code == 400
    assert response.json() == {"detail": "invalid correlation id"}


def test_unstarted_app_refuses_requests_instead_of_rereading_process_environment(monkeypatch):
    app = create_app()
    monkeypatch.setenv("EIP_BACKEND", "azure")

    response = TestClient(app).get("/healthz")

    assert response.status_code == 503
    assert response.json()["status"] == "unavailable"
    assert "not bound" in response.json()["detail"]


def test_invalid_trace_headers_are_not_reflected_to_downstream_adapters_or_responses():
    app = create_app(ApplicationSettings.from_mapping({}))

    with TestClient(app) as client:
        response = client.get("/healthz", headers={"traceparent": "not-a-trace"})

    assert response.status_code == 200
    assert response.headers["traceparent"] != "not-a-trace"
    assert TraceContext.from_headers(response.headers).traceparent == response.headers["traceparent"]
