"""Machine-checkable performance targets and observation artifacts.

The source of truth is ``requirements/performance-baseline.json``.  It is a
*target* contract: loading it or validating an observation never establishes
production readiness.  A real observation must still be retained through the
immutable evidence registry described in ``docs/PRODUCTION-EVIDENCE.md``.

Keeping the target and the observed result separate is deliberate.  It avoids
turning a checked-in JSON fixture into a claim that a latency, queue, cost, or
lease objective has been achieved in a named environment.
"""
from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from validation.evidence_records import BASES, DECISIONS


SCHEMA_VERSION = 1
IMPLEMENTATION_STATES = frozenset({"reference", "target"})
AUTONOMY_TIERS = frozenset({"L0", "L1", "L2", "L3", "L4"})
EXECUTION_MODELS = frozenset({"synchronous", "asynchronous", "durable"})

# Names are intentionally low-cardinality and report-level.  A performance
# artifact must never contain request text, PR content, evidence payloads, or
# a user identifier merely to explain one latency measurement.
LATENCY_METRICS = frozenset(
    {"p50_latency_ms", "p95_latency_ms", "p99_latency_ms", "max_latency_ms"}
)
RATE_METRICS = frozenset(
    {"success_rate", "audit_write_success_rate", "verification_success_rate"}
)
COUNT_METRICS = frozenset(
    {"peak_in_flight", "peak_queue_depth", "rejected_count"}
)
NONNEGATIVE_METRICS = frozenset(
    {"peak_queue_age_seconds", "unit_cost_usd"}
)
KNOWN_METRICS = LATENCY_METRICS | RATE_METRICS | COUNT_METRICS | NONNEGATIVE_METRICS
BASE_REQUIRED_METRICS = frozenset(
    {
        "p50_latency_ms",
        "p95_latency_ms",
        "p99_latency_ms",
        "max_latency_ms",
        "success_rate",
        "peak_in_flight",
        "rejected_count",
        "unit_cost_usd",
    }
)


class PerformanceContractError(ValueError):
    """A performance contract or observation is malformed."""


@dataclass(frozen=True)
class StepBudget:
    name: str
    p95_ms: int
    p99_ms: int
    timeout_ms: int


@dataclass(frozen=True)
class Targets:
    p95_latency_ms: int
    p99_latency_ms: int
    timeout_ms: int
    minimum_rates: Mapping[str, float]
    maximum_rejected_rate: float
    maximum_unit_cost_usd: float


@dataclass(frozen=True)
class LoadBudget:
    sustained_per_minute: int
    max_in_flight: int
    max_queue_depth: int
    max_queue_age_seconds: int
    load_shed: str


@dataclass(frozen=True)
class LeaseBudget:
    lease_seconds: int
    heartbeat_interval_seconds: int
    approval_wait_outside_lease: bool


@dataclass(frozen=True)
class EvidenceRequirements:
    minimum_samples: int
    minimum_window_minutes: int
    required_metrics: tuple[str, ...]


@dataclass(frozen=True)
class WorkflowPerformanceContract:
    contract_id: str
    workflow: str
    surface: str
    autonomy_tier: str
    implementation_state: str
    promotion_decision: str
    execution_model: str
    targets: Targets
    steps: tuple[StepBudget, ...]
    load: LoadBudget
    lease: LeaseBudget | None
    evidence: EvidenceRequirements


@dataclass(frozen=True)
class PerformanceBaseline:
    status: str
    contracts: tuple[WorkflowPerformanceContract, ...]

    def contract(self, contract_id: str) -> WorkflowPerformanceContract:
        for contract in self.contracts:
            if contract.contract_id == contract_id:
                return contract
        raise PerformanceContractError(f"unknown performance contract: {contract_id}")


@dataclass(frozen=True)
class PerformanceObservation:
    contract_id: str
    scope: str
    change: str
    basis: str
    source_run_url: str | None
    started_at: datetime
    ended_at: datetime
    sample_count: int
    metrics: Mapping[str, float | int]
    artifacts: tuple[str, ...]
    known_limitations: str


@dataclass(frozen=True)
class PerformanceAssessment:
    contract_id: str
    meets_target: bool
    violations: tuple[str, ...]


def _mapping(value: object, context: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise PerformanceContractError(f"{context}: must be a JSON object")
    return value


def _check_keys(
    mapping: Mapping[str, object], *, required: frozenset[str], allowed: frozenset[str], context: str
) -> None:
    missing = sorted(required - set(mapping))
    unknown = sorted(set(mapping) - allowed)
    problems: list[str] = []
    if missing:
        problems.append("missing " + ", ".join(missing))
    if unknown:
        problems.append("unknown " + ", ".join(unknown))
    if problems:
        raise PerformanceContractError(f"{context}: " + "; ".join(problems))


def _text(mapping: Mapping[str, object], field: str, context: str) -> str:
    value = mapping[field]
    if not isinstance(value, str) or not value.strip():
        raise PerformanceContractError(f"{context}.{field}: must be a non-blank string")
    return value.strip()


def _integer(mapping: Mapping[str, object], field: str, context: str, *, minimum: int = 0) -> int:
    value = mapping[field]
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        raise PerformanceContractError(f"{context}.{field}: must be an integer >= {minimum}")
    return value


def _number(mapping: Mapping[str, object], field: str, context: str, *, minimum: float = 0.0) -> float:
    value = mapping[field]
    if not isinstance(value, (int, float)) or isinstance(value, bool) or float(value) < minimum:
        raise PerformanceContractError(f"{context}.{field}: must be a number >= {minimum:g}")
    return float(value)


def _rate(mapping: Mapping[str, object], field: str, context: str) -> float:
    value = _number(mapping, field, context)
    if value > 1.0:
        raise PerformanceContractError(f"{context}.{field}: must be between 0 and 1")
    return value


def _string_list(
    mapping: Mapping[str, object], field: str, context: str, *, allowed: frozenset[str] | None = None
) -> tuple[str, ...]:
    value = mapping[field]
    if not isinstance(value, list) or not value:
        raise PerformanceContractError(f"{context}.{field}: must be a non-empty list")
    items: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise PerformanceContractError(f"{context}.{field}: entries must be non-blank strings")
        normalized = item.strip()
        if normalized in items:
            raise PerformanceContractError(f"{context}.{field}: entries must be unique")
        if allowed is not None and normalized not in allowed:
            raise PerformanceContractError(
                f"{context}.{field}: unknown value {normalized!r}; expected one of {', '.join(sorted(allowed))}"
            )
        items.append(normalized)
    return tuple(items)


def _parse_steps(value: object, context: str) -> tuple[StepBudget, ...]:
    if not isinstance(value, list) or not value:
        raise PerformanceContractError(f"{context}.steps: must be a non-empty list")
    steps: list[StepBudget] = []
    names: set[str] = set()
    for index, raw_step in enumerate(value):
        step_context = f"{context}.steps[{index}]"
        mapping = _mapping(raw_step, step_context)
        _check_keys(
            mapping,
            required=frozenset({"name", "p95_ms", "p99_ms", "timeout_ms"}),
            allowed=frozenset({"name", "p95_ms", "p99_ms", "timeout_ms"}),
            context=step_context,
        )
        name = _text(mapping, "name", step_context)
        if name in names:
            raise PerformanceContractError(f"{step_context}.name: duplicate step {name!r}")
        p95 = _integer(mapping, "p95_ms", step_context, minimum=1)
        p99 = _integer(mapping, "p99_ms", step_context, minimum=1)
        timeout = _integer(mapping, "timeout_ms", step_context, minimum=1)
        if not p95 <= p99 < timeout:
            raise PerformanceContractError(
                f"{step_context}: require p95_ms <= p99_ms < timeout_ms"
            )
        names.add(name)
        steps.append(StepBudget(name=name, p95_ms=p95, p99_ms=p99, timeout_ms=timeout))
    return tuple(steps)


def _parse_targets(value: object, context: str) -> Targets:
    mapping = _mapping(value, f"{context}.targets")
    target_context = f"{context}.targets"
    _check_keys(
        mapping,
        required=frozenset(
            {
                "p95_latency_ms",
                "p99_latency_ms",
                "timeout_ms",
                "minimum_rates",
                "maximum_rejected_rate",
                "maximum_unit_cost_usd",
            }
        ),
        allowed=frozenset(
            {
                "p95_latency_ms",
                "p99_latency_ms",
                "timeout_ms",
                "minimum_rates",
                "maximum_rejected_rate",
                "maximum_unit_cost_usd",
            }
        ),
        context=target_context,
    )
    p95 = _integer(mapping, "p95_latency_ms", target_context, minimum=1)
    p99 = _integer(mapping, "p99_latency_ms", target_context, minimum=1)
    timeout = _integer(mapping, "timeout_ms", target_context, minimum=1)
    if not p95 <= p99 < timeout:
        raise PerformanceContractError(f"{target_context}: require p95_latency_ms <= p99_latency_ms < timeout_ms")
    raw_rates = _mapping(mapping["minimum_rates"], f"{target_context}.minimum_rates")
    if not raw_rates:
        raise PerformanceContractError(f"{target_context}.minimum_rates: must not be empty")
    rates: dict[str, float] = {}
    for name, value in raw_rates.items():
        if name not in RATE_METRICS:
            raise PerformanceContractError(f"{target_context}.minimum_rates: unknown rate {name!r}")
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not 0 <= float(value) <= 1:
            raise PerformanceContractError(
                f"{target_context}.minimum_rates.{name}: must be between 0 and 1"
            )
        rates[name] = float(value)
    if "success_rate" not in rates:
        raise PerformanceContractError(f"{target_context}.minimum_rates: success_rate is required")
    return Targets(
        p95_latency_ms=p95,
        p99_latency_ms=p99,
        timeout_ms=timeout,
        minimum_rates=dict(sorted(rates.items())),
        maximum_rejected_rate=_rate(mapping, "maximum_rejected_rate", target_context),
        maximum_unit_cost_usd=_number(mapping, "maximum_unit_cost_usd", target_context),
    )


def _parse_load(value: object, context: str) -> LoadBudget:
    mapping = _mapping(value, f"{context}.load")
    load_context = f"{context}.load"
    _check_keys(
        mapping,
        required=frozenset(
            {
                "sustained_per_minute",
                "max_in_flight",
                "max_queue_depth",
                "max_queue_age_seconds",
                "load_shed",
            }
        ),
        allowed=frozenset(
            {
                "sustained_per_minute",
                "max_in_flight",
                "max_queue_depth",
                "max_queue_age_seconds",
                "load_shed",
            }
        ),
        context=load_context,
    )
    queue_depth = _integer(mapping, "max_queue_depth", load_context)
    queue_age = _integer(mapping, "max_queue_age_seconds", load_context)
    if queue_depth == 0 and queue_age != 0:
        raise PerformanceContractError(
            f"{load_context}: max_queue_age_seconds must be 0 when max_queue_depth is 0"
        )
    return LoadBudget(
        sustained_per_minute=_integer(mapping, "sustained_per_minute", load_context, minimum=1),
        max_in_flight=_integer(mapping, "max_in_flight", load_context, minimum=1),
        max_queue_depth=queue_depth,
        max_queue_age_seconds=queue_age,
        load_shed=_text(mapping, "load_shed", load_context),
    )


def _parse_lease(value: object, context: str, targets: Targets) -> LeaseBudget | None:
    if value is None:
        return None
    lease_context = f"{context}.lease"
    mapping = _mapping(value, lease_context)
    _check_keys(
        mapping,
        required=frozenset(
            {"lease_seconds", "heartbeat_interval_seconds", "approval_wait_outside_lease"}
        ),
        allowed=frozenset(
            {"lease_seconds", "heartbeat_interval_seconds", "approval_wait_outside_lease"}
        ),
        context=lease_context,
    )
    lease_seconds = _integer(mapping, "lease_seconds", lease_context, minimum=1)
    heartbeat = _integer(mapping, "heartbeat_interval_seconds", lease_context, minimum=1)
    wait_outside = mapping["approval_wait_outside_lease"]
    if not isinstance(wait_outside, bool):
        raise PerformanceContractError(f"{lease_context}.approval_wait_outside_lease: must be a boolean")
    active_timeout_seconds = (targets.timeout_ms + 999) // 1000
    if heartbeat >= lease_seconds:
        raise PerformanceContractError(
            f"{lease_context}: heartbeat_interval_seconds must be shorter than lease_seconds"
        )
    if lease_seconds < active_timeout_seconds + heartbeat:
        raise PerformanceContractError(
            f"{lease_context}: lease_seconds must cover timeout_ms plus one heartbeat interval"
        )
    return LeaseBudget(
        lease_seconds=lease_seconds,
        heartbeat_interval_seconds=heartbeat,
        approval_wait_outside_lease=wait_outside,
    )


def _parse_evidence(value: object, context: str, *, load: LoadBudget, targets: Targets) -> EvidenceRequirements:
    mapping = _mapping(value, f"{context}.evidence")
    evidence_context = f"{context}.evidence"
    _check_keys(
        mapping,
        required=frozenset({"minimum_samples", "minimum_window_minutes", "required_metrics"}),
        allowed=frozenset({"minimum_samples", "minimum_window_minutes", "required_metrics"}),
        context=evidence_context,
    )
    metrics = _string_list(mapping, "required_metrics", evidence_context, allowed=KNOWN_METRICS)
    required = set(metrics)
    missing_base = sorted(BASE_REQUIRED_METRICS - required)
    if missing_base:
        raise PerformanceContractError(
            f"{evidence_context}.required_metrics: missing base metrics {', '.join(missing_base)}"
        )
    if load.max_queue_depth > 0:
        queue_metrics = {"peak_queue_depth", "peak_queue_age_seconds"}
        if missing := sorted(queue_metrics - required):
            raise PerformanceContractError(
                f"{evidence_context}.required_metrics: queued workflow missing {', '.join(missing)}"
            )
    if missing_rates := sorted(set(targets.minimum_rates) - required):
        raise PerformanceContractError(
            f"{evidence_context}.required_metrics: rate target missing {', '.join(missing_rates)}"
        )
    return EvidenceRequirements(
        minimum_samples=_integer(mapping, "minimum_samples", evidence_context, minimum=1),
        minimum_window_minutes=_integer(mapping, "minimum_window_minutes", evidence_context, minimum=1),
        required_metrics=metrics,
    )


def _parse_contract(value: object, index: int) -> WorkflowPerformanceContract:
    context = f"contracts[{index}]"
    mapping = _mapping(value, context)
    required = frozenset(
        {
            "id",
            "workflow",
            "surface",
            "autonomy_tier",
            "implementation_state",
            "promotion_decision",
            "execution_model",
            "targets",
            "steps",
            "load",
            "lease",
            "evidence",
        }
    )
    _check_keys(mapping, required=required, allowed=required, context=context)
    autonomy_tier = _text(mapping, "autonomy_tier", context)
    if autonomy_tier not in AUTONOMY_TIERS:
        raise PerformanceContractError(f"{context}.autonomy_tier: expected one of {', '.join(sorted(AUTONOMY_TIERS))}")
    state = _text(mapping, "implementation_state", context)
    if state not in IMPLEMENTATION_STATES:
        raise PerformanceContractError(
            f"{context}.implementation_state: expected one of {', '.join(sorted(IMPLEMENTATION_STATES))}"
        )
    decision = _text(mapping, "promotion_decision", context)
    if decision not in DECISIONS:
        raise PerformanceContractError(f"{context}.promotion_decision: expected one of {', '.join(DECISIONS)}")
    execution_model = _text(mapping, "execution_model", context)
    if execution_model not in EXECUTION_MODELS:
        raise PerformanceContractError(
            f"{context}.execution_model: expected one of {', '.join(sorted(EXECUTION_MODELS))}"
        )
    targets = _parse_targets(mapping["targets"], context)
    steps = _parse_steps(mapping["steps"], context)
    if sum(step.p95_ms for step in steps) > targets.p95_latency_ms:
        raise PerformanceContractError(f"{context}.steps: p95 sum exceeds end-to-end target")
    if sum(step.p99_ms for step in steps) > targets.p99_latency_ms:
        raise PerformanceContractError(f"{context}.steps: p99 sum exceeds end-to-end target")
    if any(step.timeout_ms > targets.timeout_ms for step in steps):
        raise PerformanceContractError(f"{context}.steps: a step timeout exceeds the end-to-end timeout")
    load = _parse_load(mapping["load"], context)
    lease = _parse_lease(mapping["lease"], context, targets)
    if autonomy_tier in {"L3", "L4"}:
        if execution_model != "durable" or lease is None:
            raise PerformanceContractError(
                f"{context}: {autonomy_tier} requires a durable execution model and lease budget"
            )
        if not lease.approval_wait_outside_lease:
            raise PerformanceContractError(
                f"{context}.lease: human approval waits must remain outside the active lease"
            )
    evidence = _parse_evidence(mapping["evidence"], context, load=load, targets=targets)
    return WorkflowPerformanceContract(
        contract_id=_text(mapping, "id", context),
        workflow=_text(mapping, "workflow", context),
        surface=_text(mapping, "surface", context),
        autonomy_tier=autonomy_tier,
        implementation_state=state,
        promotion_decision=decision,
        execution_model=execution_model,
        targets=targets,
        steps=steps,
        load=load,
        lease=lease,
        evidence=evidence,
    )


def load_performance_baseline(path: str | Path) -> PerformanceBaseline:
    """Load and fully validate the canonical target performance contract."""

    source = Path(path)
    try:
        payload: object = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise PerformanceContractError(f"cannot read performance baseline {source}: {error}") from error
    mapping = _mapping(payload, "performance baseline")
    required = frozenset({"schema_version", "status", "contracts"})
    _check_keys(mapping, required=required, allowed=required, context="performance baseline")
    version = _integer(mapping, "schema_version", "performance baseline", minimum=1)
    if version != SCHEMA_VERSION:
        raise PerformanceContractError(
            f"performance baseline.schema_version: expected {SCHEMA_VERSION}, got {version}"
        )
    status = _text(mapping, "status", "performance baseline")
    if status != "target":
        raise PerformanceContractError("performance baseline.status: must be 'target'")
    raw_contracts = mapping["contracts"]
    if not isinstance(raw_contracts, list) or not raw_contracts:
        raise PerformanceContractError("performance baseline.contracts: must be a non-empty list")
    contracts = tuple(_parse_contract(raw, index) for index, raw in enumerate(raw_contracts))
    ids = [contract.contract_id for contract in contracts]
    if len(ids) != len(set(ids)):
        raise PerformanceContractError("performance baseline.contracts: ids must be unique")
    return PerformanceBaseline(status=status, contracts=contracts)


def _parse_timestamp(value: object, context: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise PerformanceContractError(f"{context}: must be a non-blank ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise PerformanceContractError(f"{context}: must be an ISO-8601 timestamp") from error
    if parsed.tzinfo is None:
        raise PerformanceContractError(f"{context}: timestamp must include a timezone")
    return parsed


def _parse_metrics(value: object, contract: WorkflowPerformanceContract) -> Mapping[str, float | int]:
    context = "observation.metrics"
    mapping = _mapping(value, context)
    unknown = sorted(set(mapping) - KNOWN_METRICS)
    missing = sorted(set(contract.evidence.required_metrics) - set(mapping))
    if unknown or missing:
        details: list[str] = []
        if missing:
            details.append("missing " + ", ".join(missing))
        if unknown:
            details.append("unknown " + ", ".join(unknown))
        raise PerformanceContractError(f"{context}: " + "; ".join(details))
    metrics: dict[str, float | int] = {}
    for name, value in mapping.items():
        if name in RATE_METRICS:
            if not isinstance(value, (int, float)) or isinstance(value, bool) or not 0 <= float(value) <= 1:
                raise PerformanceContractError(f"{context}.{name}: must be a rate between 0 and 1")
            metrics[name] = float(value)
        elif name in COUNT_METRICS:
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise PerformanceContractError(f"{context}.{name}: must be a non-negative integer")
            metrics[name] = value
        else:
            if not isinstance(value, (int, float)) or isinstance(value, bool) or float(value) < 0:
                raise PerformanceContractError(f"{context}.{name}: must be a non-negative number")
            metrics[name] = float(value)
    p50 = float(metrics["p50_latency_ms"])
    p95 = float(metrics["p95_latency_ms"])
    p99 = float(metrics["p99_latency_ms"])
    maximum = float(metrics["max_latency_ms"])
    if not p50 <= p95 <= p99 <= maximum:
        raise PerformanceContractError(
            "observation.metrics: require p50_latency_ms <= p95_latency_ms <= p99_latency_ms <= max_latency_ms"
        )
    return dict(sorted(metrics.items()))


def validate_performance_observation(
    mapping: Mapping[str, object], baseline: PerformanceBaseline
) -> PerformanceObservation:
    """Validate a report artifact without treating it as a promotion decision."""

    context = "observation"
    required = frozenset(
        {
            "contract_id",
            "scope",
            "change",
            "basis",
            "window",
            "sample_count",
            "metrics",
            "artifacts",
            "known_limitations",
        }
    )
    allowed = required | {"source_run_url"}
    _check_keys(mapping, required=required, allowed=allowed, context=context)
    contract_id = _text(mapping, "contract_id", context)
    contract = baseline.contract(contract_id)
    basis = _text(mapping, "basis", context)
    if basis not in BASES:
        raise PerformanceContractError(f"{context}.basis: expected one of {', '.join(BASES)}")
    source_run_url = mapping.get("source_run_url")
    if source_run_url is not None:
        if not isinstance(source_run_url, str) or not source_run_url.startswith("https://"):
            raise PerformanceContractError(f"{context}.source_run_url: must be an https URL when present")
    if basis == "measured" and source_run_url is None:
        raise PerformanceContractError(f"{context}.source_run_url: required when basis is measured")
    window = _mapping(mapping["window"], f"{context}.window")
    _check_keys(
        window,
        required=frozenset({"started_at", "ended_at"}),
        allowed=frozenset({"started_at", "ended_at"}),
        context=f"{context}.window",
    )
    started_at = _parse_timestamp(window["started_at"], f"{context}.window.started_at")
    ended_at = _parse_timestamp(window["ended_at"], f"{context}.window.ended_at")
    if ended_at <= started_at:
        raise PerformanceContractError(f"{context}.window: ended_at must be later than started_at")
    artifacts = _string_list(mapping, "artifacts", context)
    if any(not artifact.startswith("https://") for artifact in artifacts):
        raise PerformanceContractError(f"{context}.artifacts: entries must be https URLs or retained artifact links")
    sample_count = _integer(mapping, "sample_count", context, minimum=1)
    metrics = _parse_metrics(mapping["metrics"], contract)
    rejected = int(metrics["rejected_count"])
    if rejected > sample_count:
        raise PerformanceContractError("observation.metrics.rejected_count: cannot exceed sample_count")
    return PerformanceObservation(
        contract_id=contract_id,
        scope=_text(mapping, "scope", context),
        change=_text(mapping, "change", context),
        basis=basis,
        source_run_url=source_run_url,
        started_at=started_at,
        ended_at=ended_at,
        sample_count=sample_count,
        metrics=metrics,
        artifacts=artifacts,
        known_limitations=_text(mapping, "known_limitations", context),
    )


def assess_performance_observation(
    observation: PerformanceObservation, baseline: PerformanceBaseline
) -> PerformanceAssessment:
    """Compare a structurally valid observation to its target contract.

    The result is only a target comparison.  It neither writes an evidence
    record nor changes a capability/autonomy state.
    """

    contract = baseline.contract(observation.contract_id)
    violations: list[str] = []
    window_minutes = (observation.ended_at - observation.started_at).total_seconds() / 60
    if observation.sample_count < contract.evidence.minimum_samples:
        violations.append(
            f"sample_count {observation.sample_count} < required {contract.evidence.minimum_samples}"
        )
    if window_minutes < contract.evidence.minimum_window_minutes:
        violations.append(
            f"window {window_minutes:g}m < required {contract.evidence.minimum_window_minutes}m"
        )
    metrics = observation.metrics
    if float(metrics["p95_latency_ms"]) > contract.targets.p95_latency_ms:
        violations.append(
            f"p95_latency_ms {float(metrics['p95_latency_ms']):g} > target {contract.targets.p95_latency_ms}"
        )
    if float(metrics["p99_latency_ms"]) > contract.targets.p99_latency_ms:
        violations.append(
            f"p99_latency_ms {float(metrics['p99_latency_ms']):g} > target {contract.targets.p99_latency_ms}"
        )
    if float(metrics["max_latency_ms"]) > contract.targets.timeout_ms:
        violations.append(
            f"max_latency_ms {float(metrics['max_latency_ms']):g} > timeout {contract.targets.timeout_ms}"
        )
    for name, minimum in contract.targets.minimum_rates.items():
        actual = float(metrics[name])
        if actual < minimum:
            violations.append(f"{name} {actual:g} < target {minimum:g}")
    rejected_rate = int(metrics["rejected_count"]) / observation.sample_count
    if rejected_rate > contract.targets.maximum_rejected_rate:
        violations.append(
            f"rejected_rate {rejected_rate:g} > target {contract.targets.maximum_rejected_rate:g}"
        )
    if int(metrics["peak_in_flight"]) > contract.load.max_in_flight:
        violations.append(
            f"peak_in_flight {metrics['peak_in_flight']} > limit {contract.load.max_in_flight}"
        )
    if "peak_queue_depth" in metrics and int(metrics["peak_queue_depth"]) > contract.load.max_queue_depth:
        violations.append(
            f"peak_queue_depth {metrics['peak_queue_depth']} > limit {contract.load.max_queue_depth}"
        )
    if (
        "peak_queue_age_seconds" in metrics
        and float(metrics["peak_queue_age_seconds"]) > contract.load.max_queue_age_seconds
    ):
        violations.append(
            "peak_queue_age_seconds "
            f"{float(metrics['peak_queue_age_seconds']):g} > limit {contract.load.max_queue_age_seconds}"
        )
    if float(metrics["unit_cost_usd"]) > contract.targets.maximum_unit_cost_usd:
        violations.append(
            f"unit_cost_usd {float(metrics['unit_cost_usd']):g} > target {contract.targets.maximum_unit_cost_usd:g}"
        )
    return PerformanceAssessment(
        contract_id=contract.contract_id,
        meets_target=not violations,
        violations=tuple(violations),
    )


def render_contract_tables(baseline: PerformanceBaseline) -> str:
    """Render the canonical Markdown tables embedded in the companion document."""

    rows = [
        "| ID | Workflow | State | Tier | End-to-end p95 / p99 / timeout | Load and shed limit | Lease | Evidence sample / window |",
        "|---|---|---|---|---|---|---|---|",
    ]
    step_rows = [
        "| Contract | Step | p95 | p99 | timeout |",
        "|---|---|---:|---:|---:|",
    ]
    for contract in baseline.contracts:
        targets = contract.targets
        load = contract.load
        if contract.lease is None:
            lease = "No durable lease (reference path)"
        else:
            lease = (
                f"{contract.lease.lease_seconds}s; heartbeat {contract.lease.heartbeat_interval_seconds}s; "
                "approval outside lease"
            )
        rows.append(
            "| "
            + " | ".join(
                (
                    contract.contract_id,
                    contract.workflow,
                    contract.implementation_state,
                    contract.autonomy_tier,
                    f"{targets.p95_latency_ms} / {targets.p99_latency_ms} / {targets.timeout_ms} ms",
                    f"{load.sustained_per_minute}/min; {load.max_in_flight} in-flight; "
                    f"queue {load.max_queue_depth}/{load.max_queue_age_seconds}s",
                    lease,
                    f"{contract.evidence.minimum_samples} / {contract.evidence.minimum_window_minutes} min",
                )
            )
            + " |"
        )
        for step in contract.steps:
            step_rows.append(
                f"| {contract.contract_id} | {step.name} | {step.p95_ms} ms | {step.p99_ms} ms | {step.timeout_ms} ms |"
            )
    return "\n".join(rows + [""] + step_rows)


def rendered_document_matches(document: str | Path, baseline: PerformanceBaseline) -> bool:
    """Return whether the marker-delimited tables match the canonical JSON exactly."""

    start = "<!-- PERFORMANCE-CONTRACT-TABLE:START -->"
    end = "<!-- PERFORMANCE-CONTRACT-TABLE:END -->"
    text = Path(document).read_text(encoding="utf-8")
    if text.count(start) != 1 or text.count(end) != 1:
        raise PerformanceContractError("performance document must contain one start and one end table marker")
    content = text.split(start, 1)[1].split(end, 1)[0].strip()
    return content == render_contract_tables(baseline)
