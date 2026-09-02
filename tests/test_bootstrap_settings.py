from dataclasses import FrozenInstanceError

import pytest

from app.bootstrap_settings import BootstrapSettings


def test_bootstrap_settings_normalize_optional_otlp_endpoint():
    assert BootstrapSettings.from_mapping({}).otlp_endpoint is None
    assert BootstrapSettings.from_mapping({"OTEL_EXPORTER_OTLP_ENDPOINT": "   "}).otlp_endpoint is None
    assert (
        BootstrapSettings.from_mapping(
            {"OTEL_EXPORTER_OTLP_ENDPOINT": " https://otel.internal:4318 "}
        ).otlp_endpoint
        == "https://otel.internal:4318"
    )


def test_bootstrap_settings_are_immutable():
    settings = BootstrapSettings.from_mapping(
        {"OTEL_EXPORTER_OTLP_ENDPOINT": "https://otel.internal:4318"}
    )
    with pytest.raises(FrozenInstanceError):
        settings.otlp_endpoint = "https://other.invalid"
