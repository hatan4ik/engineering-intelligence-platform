from __future__ import annotations

import pytest

from control_plane.correlation import CorrelationId, resolve_correlation_id


def test_provided_identifier_is_preserved_after_whitespace_is_trimmed():
    correlation_id = resolve_correlation_id("  upstream:run-42  ")

    assert correlation_id == "upstream:run-42"
    assert isinstance(correlation_id, str)


@pytest.mark.parametrize("invalid", ("", "contains space", "newline\nvalue", "?query", "x" * 129))
def test_untrusted_identifier_is_rejected_before_it_reaches_audit_or_telemetry(invalid):
    with pytest.raises(ValueError, match="invalid correlation id"):
        resolve_correlation_id(invalid)


def test_missing_identifier_mints_a_bounded_correlation_id():
    correlation_id: CorrelationId = resolve_correlation_id()

    assert len(correlation_id) == 36
    assert "-" in correlation_id
