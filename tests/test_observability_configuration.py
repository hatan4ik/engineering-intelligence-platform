"""OTLP bootstrap preserves the standard base-endpoint signal paths."""

from app.observability import _signal_endpoint


def test_otlp_base_endpoint_is_expanded_to_its_signal_path():
    assert _signal_endpoint("https://collector.example.invalid", "traces") == (
        "https://collector.example.invalid/v1/traces"
    )
    assert _signal_endpoint("https://collector.example.invalid/", "metrics") == (
        "https://collector.example.invalid/v1/metrics"
    )
