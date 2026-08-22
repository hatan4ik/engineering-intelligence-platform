from intelligence.app_insights import (
    correlated_operation_failures,
    from_app_insights_dependency,
    from_app_insights_exception,
    from_app_insights_request,
    from_otel_span,
)


def test_app_insights_request_dependency_exception_normalize_as_evidence():
    request = from_app_insights_request({
        "id": "req-1", "timestamp": "2026-08-22T10:00:00Z", "name": "POST /checkout",
        "success": "false", "resultCode": "500", "duration": "00:00:01.2", "operation_Id": "op-7",
    }, service="checkout")
    dependency = from_app_insights_dependency({
        "id": "dep-1", "timestamp": "2026-08-22T10:00:00.2Z", "target": "payments",
        "type": "HTTP", "name": "POST /charge", "success": "false", "resultCode": "503",
        "operation_Id": "op-7",
    }, service="checkout")
    exception = from_app_insights_exception({
        "id": "exc-1", "timestamp": "2026-08-22T10:00:00.4Z", "type": "PaymentUnavailable",
        "outerMessage": "upstream unavailable", "operation_Id": "op-7",
    }, service="checkout")

    assert request.severity == 4
    assert dependency.severity == 4
    assert exception.severity == 5
    grouped = correlated_operation_failures([request, dependency, exception])
    assert grouped["op-7"] == ("req-1", "dep-1", "exc-1")


def test_otel_span_normalizes_selected_semantic_attributes():
    event = from_otel_span({
        "span_id": "span-1",
        "name": "POST /charge",
        "start_time": "2026-08-22T10:00:00Z",
        "status": {"code": "ERROR"},
        "attributes": {
            "http.response.status_code": 503,
            "server.address": "payments.internal",
            "secret": "do-not-copy",
        },
    }, service="checkout")
    assert event.severity == 4
    assert ("http.response.status_code", "503") in event.attributes
    assert all(key != "secret" for key, _ in event.attributes)


def test_telemetry_without_timestamp_fails_closed():
    try:
        from_app_insights_request({"id": "x"}, service="checkout")
    except ValueError as exc:
        assert "timestamp" in str(exc)
    else:
        raise AssertionError("missing timestamp accepted")
