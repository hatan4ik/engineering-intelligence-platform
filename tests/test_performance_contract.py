"""The performance baseline is a validated target, never synthetic evidence."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.validate_performance_observation import main as validate_observation_main
from validation.performance_contract import (
    PerformanceContractError,
    assess_performance_observation,
    load_performance_baseline,
    rendered_document_matches,
    validate_performance_observation,
)


ROOT = Path(__file__).resolve().parents[1]
BASELINE_PATH = ROOT / "requirements" / "performance-baseline.json"
DOCUMENT_PATH = ROOT / "docs" / "PERFORMANCE-EVIDENCE-CONTRACT.md"


def _observation(contract_id: str = "EIP-PERF-PRG-001") -> dict[str, object]:
    baseline = load_performance_baseline(BASELINE_PATH)
    contract = baseline.contract(contract_id)
    metrics: dict[str, float | int] = {
        "p50_latency_ms": 1000.0,
        "p95_latency_ms": float(contract.targets.p95_latency_ms),
        "p99_latency_ms": float(contract.targets.p99_latency_ms),
        "max_latency_ms": float(contract.targets.timeout_ms - 1),
        "success_rate": contract.targets.minimum_rates["success_rate"],
        "peak_in_flight": contract.load.max_in_flight,
        "rejected_count": 0,
        "unit_cost_usd": contract.targets.maximum_unit_cost_usd,
    }
    if "peak_queue_depth" in contract.evidence.required_metrics:
        metrics["peak_queue_depth"] = contract.load.max_queue_depth
        metrics["peak_queue_age_seconds"] = contract.load.max_queue_age_seconds
    for rate in contract.targets.minimum_rates:
        metrics[rate] = contract.targets.minimum_rates[rate]
    return {
        "contract_id": contract_id,
        "scope": "owner/repository, integration, westeurope, internal, L1",
        "change": "sha=abc image=sha256:def policy=eip-remediation-v1",
        "basis": "measured",
        "source_run_url": "https://evidence.example.invalid/runs/123",
        "window": {
            "started_at": "2026-09-01T00:00:00+00:00",
            "ended_at": "2026-10-01T00:00:00+00:00",
        },
        "sample_count": contract.evidence.minimum_samples,
        "metrics": metrics,
        "artifacts": ["https://evidence.example.invalid/reports/123#sha256:abc"],
        "known_limitations": "Representative integration workload; not a production claim.",
    }


def test_checked_in_baseline_is_a_target_with_five_explicit_workflows():
    baseline = load_performance_baseline(BASELINE_PATH)

    assert baseline.status == "target"
    assert [contract.contract_id for contract in baseline.contracts] == [
        "EIP-PERF-QUERY-001",
        "EIP-PERF-PRG-001",
        "EIP-PERF-OPS-001",
        "EIP-PERF-L3-001",
        "EIP-PERF-L4-001",
    ]
    assert {contract.implementation_state for contract in baseline.contracts} == {"reference", "target"}


def test_l3_and_l4_lease_targets_are_not_the_local_60_second_reference_default():
    baseline = load_performance_baseline(BASELINE_PATH)

    for contract_id in ("EIP-PERF-L3-001", "EIP-PERF-L4-001"):
        contract = baseline.contract(contract_id)
        assert contract.execution_model == "durable"
        assert contract.lease is not None
        assert contract.lease.lease_seconds > 60
        assert contract.lease.lease_seconds >= (
            (contract.targets.timeout_ms + 999) // 1000
        ) + contract.lease.heartbeat_interval_seconds
        assert contract.lease.approval_wait_outside_lease is True


def test_rendered_tables_are_derived_from_the_canonical_json_baseline():
    baseline = load_performance_baseline(BASELINE_PATH)

    assert rendered_document_matches(DOCUMENT_PATH, baseline) is True


def test_measured_observation_can_meet_its_target_without_becoming_a_promotion_decision():
    baseline = load_performance_baseline(BASELINE_PATH)
    observation = validate_performance_observation(_observation(), baseline)

    assessment = assess_performance_observation(observation, baseline)

    assert assessment.contract_id == "EIP-PERF-PRG-001"
    assert assessment.meets_target is True
    assert assessment.violations == ()


def test_valid_observation_that_misses_a_target_is_not_mislabeled_as_invalid():
    baseline = load_performance_baseline(BASELINE_PATH)
    payload = _observation()
    metrics = payload["metrics"]
    assert isinstance(metrics, dict)
    metrics["p95_latency_ms"] = 20_001

    assessment = assess_performance_observation(
        validate_performance_observation(payload, baseline), baseline
    )

    assert assessment.meets_target is False
    assert assessment.violations == ("p95_latency_ms 20001 > target 20000",)


def test_measured_observation_requires_a_source_run_url():
    baseline = load_performance_baseline(BASELINE_PATH)
    payload = _observation()
    payload.pop("source_run_url")

    with pytest.raises(PerformanceContractError, match="source_run_url"):
        validate_performance_observation(payload, baseline)


def test_cli_reports_a_target_miss_without_writing_an_evidence_record(tmp_path, capsys):
    payload = _observation()
    metrics = payload["metrics"]
    assert isinstance(metrics, dict)
    metrics["success_rate"] = 0.5
    report = tmp_path / "performance-observation.json"
    report.write_text(json.dumps(payload), encoding="utf-8")

    code = validate_observation_main(["--input", str(report)])

    assert code == 1
    output = capsys.readouterr().out
    assert "meets_target=False" in output
    assert "success_rate 0.5 < target 0.99" in output
    assert list(tmp_path.glob("*.json")) == [report]
