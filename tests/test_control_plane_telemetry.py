from telemetry.control_plane import ControlPlaneTelemetry, project_control_plane_slo
from telemetry.events import InMemoryTelemetrySink, OperationEvent


def test_control_plane_telemetry_emits_bounded_correlated_event():
    sink = InMemoryTelemetrySink()
    telemetry = ControlPlaneTelemetry(sink, clock=lambda: 2.5)
    telemetry.emit(
        correlation_id="remediation:inc-1",
        phase="remediation.simulation",
        component="digital-twin",
        outcome="verified",
        started_at=2.0,
        service="payments",
        attributes={"runbook_id": "aks.rollout.undo"},
    )
    event = sink.events[0]
    assert event.correlation_id == "remediation:inc-1"
    assert event.latency_ms == 500.0
    assert event.agent == "control-plane"
    assert event.attributes == {"runbook_id": "aks.rollout.undo"}


def test_slo_projection_tracks_success_rollback_and_latency():
    events = [
        OperationEvent("a", "remediation.terminal", "control-plane", "succeeded", 20.0),
        OperationEvent("b", "remediation.terminal", "control-plane", "rolled_back", 40.0),
        OperationEvent("c", "remediation.terminal", "control-plane", "denied", 10.0),
        OperationEvent("noise", "retrieve", "search", "success", 999.0),
    ]
    snapshot = project_control_plane_slo(events)
    assert snapshot.total == 3
    assert snapshot.succeeded == 1
    assert snapshot.rolled_back == 1
    assert snapshot.denied == 1
    assert snapshot.success_rate == 1 / 3
    assert snapshot.rollback_rate == 1 / 3
    assert snapshot.p95_latency_ms == 40.0
