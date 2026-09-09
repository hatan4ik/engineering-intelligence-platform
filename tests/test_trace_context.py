"""Contract tests for OpenTelemetry W3C TraceContext propagation."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from intelligence.risk import RiskAssessment
from integrations.github.pr_guardian import GitHubRestPRClient, PullRequestEvent
from product.pr_guardian.contracts import (
    EvidenceBasis,
    EvidenceBundle,
    FindingAction,
    PRFinding,
)
from product.pr_guardian.telemetry import PRGuardianTelemetryRecorder
from telemetry.events import InMemoryTelemetrySink
from telemetry.trace_context import (
    TRACEPARENT_HEADER,
    TRACESTATE_HEADER,
    TraceContext,
)


VALID_TRACEPARENT = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
VALID_TRACESTATE = "congo=t61rcWkgMzE,rojo=00f067aa0ba902b7"


def test_trace_context_validates_and_normalizes_w3c_headers() -> None:
    headers = {
        TRACEPARENT_HEADER: VALID_TRACEPARENT,
        TRACESTATE_HEADER: VALID_TRACESTATE,
    }
    context = TraceContext.from_headers(headers)

    assert context.traceparent == VALID_TRACEPARENT
    assert context.tracestate == VALID_TRACESTATE
    assert context.headers() == headers


def test_trace_context_discards_invalid_traceparent() -> None:
    headers = {TRACEPARENT_HEADER: "invalid-traceparent"}
    context = TraceContext.from_headers(headers)

    assert context.traceparent is None
    assert context.tracestate is None
    assert context.headers() == {}


def test_github_rest_client_injects_traceparent_into_outbound_requests() -> None:
    client = GitHubRestPRClient(token="ghp_test_token_123")
    context = TraceContext(traceparent=VALID_TRACEPARENT, tracestate=VALID_TRACESTATE)

    with patch("telemetry.trace_context.TraceContext.current", return_value=context):
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_response = MagicMock()
            mock_response.read.return_value = b"[]"
            mock_response.__enter__.return_value = mock_response
            mock_urlopen.return_value = mock_response

            client.list_changed_files("acme/payments", 42)

            assert mock_urlopen.call_count == 1
            sent_request = mock_urlopen.call_args[0][0]
            assert sent_request.headers.get("Traceparent") == VALID_TRACEPARENT
            assert sent_request.headers.get("Tracestate") == VALID_TRACESTATE


def test_telemetry_recorder_captures_active_traceparent() -> None:
    sink = InMemoryTelemetrySink()
    recorder = PRGuardianTelemetryRecorder(sink)
    context = TraceContext(traceparent=VALID_TRACEPARENT)

    event = PullRequestEvent(
        repository="acme/payments",
        number=42,
        head_sha="deadbeef42",
        action="opened",
    )
    assessment = RiskAssessment(
        score=25,
        band="low",
        blast_radius=("payments",),
        factors=(),
    )
    finding = PRFinding(
        finding_id="pr:acme/payments:42:finding",
        repository="acme/payments",
        pr_number=42,
        head_sha="deadbeef42",
        severity="low",
        summary="Test summary",
        correlation_id="corr-42",
        policy_version="v1",
        context_version="ctx-v1",
        context_qualified=True,
        simulated_action=FindingAction.NONE,
        evidence=EvidenceBundle(
            basis=EvidenceBasis.MODELED,
            references=(),
            limitations=("No historical failures.",),
        ),
    )

    with patch("telemetry.trace_context.TraceContext.current", return_value=context):
        recorder.record(
            event=event,
            assessment=assessment,
            finding=finding,
            primary_service="payments",
            company_context=None,
            conclusion="neutral",
            latency_ms=12.5,
        )

    assert len(sink.events) == 1
    emitted = sink.events[0]
    assert emitted.attributes.get("traceparent") == VALID_TRACEPARENT
