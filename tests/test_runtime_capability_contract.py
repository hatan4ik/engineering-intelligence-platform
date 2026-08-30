"""The checked-in runtime scope stays explicit and source-consistent."""

from __future__ import annotations

import json
from dataclasses import replace

import pytest

from scripts.verify_runtime_capability_contract import (
    DEFAULT_BASELINE,
    DEFAULT_DOCUMENT,
    RuntimeCapabilityBaseline,
    RuntimeCapabilityContractError,
    load_baseline,
    rendered_document_matches,
    verify_baseline,
)


def test_runtime_capability_baseline_matches_current_sources() -> None:
    baseline = load_baseline()

    assert baseline.status == "reference-only"
    assert len(baseline.capabilities) >= 6
    assert verify_baseline(baseline) == ()


def test_rendered_runtime_capability_table_is_current() -> None:
    assert rendered_document_matches(DEFAULT_DOCUMENT, load_baseline()) is True


def test_chart_exposure_drift_is_reported_with_the_capability_id() -> None:
    baseline = load_baseline()
    query = next(item for item in baseline.capabilities if item.capability_id == "EIP-RUNTIME-API-QUERY")
    drifted = replace(query, chart=replace(query.chart, exposes=("EIP_NOT_A_REAL_VARIABLE",)))
    modified = RuntimeCapabilityBaseline(
        status=baseline.status,
        capabilities=tuple(drifted if item is query else item for item in baseline.capabilities),
    )

    errors = verify_baseline(modified)

    assert errors == (
        "EIP-RUNTIME-API-QUERY chart must expose EIP_NOT_A_REAL_VARIABLE "
        "in helm/eip/templates/deployment.yaml",
    )


def test_source_only_baseline_refuses_a_claimed_evidence_status(tmp_path) -> None:
    payload = json.loads(DEFAULT_BASELINE.read_text(encoding="utf-8"))
    payload["capabilities"][0]["evidence_status"] = "collected"
    path = tmp_path / "runtime-capabilities.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(RuntimeCapabilityContractError, match="must be not-collected"):
        load_baseline(path)
