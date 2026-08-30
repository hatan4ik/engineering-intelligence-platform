# Performance and Evidence Contract

| | |
|---|---|
| **Status** | Current design: target performance contract. It is not a measured result or a production-readiness claim. |
| **Owners** | Platform Engineering and SRE; the named service owner accepts a target for its own scope. |
| **Canonical source** | [`../requirements/performance-baseline.json`](../requirements/performance-baseline.json) |
| **Evidence registry** | [`PRODUCTION-EVIDENCE.md`](PRODUCTION-EVIDENCE.md) and [`evidence/README.md`](evidence/README.md) |
| **Operational requirement** | [`../architecture/non-functional-requirements.md`](../architecture/non-functional-requirements.md) |

## Rule

The checked-in targets below define how a workflow must be measured before a promotion review.
They are deliberately **not** reported as present performance, a service-level objective, or a
production certification. A target becomes usable only after a named scope collects a retained,
reviewable observation artifact and records the reviewed conclusion through the evidence registry.

This document covers the active attempt from accepted work to a terminal response/observation.
Queue age is measured separately. A human approval may take hours or days, but it is durable
workflow state and is never held inside an execution lease.

<!-- PERFORMANCE-CONTRACT-TABLE:START -->
| ID | Workflow | State | Tier | End-to-end p95 / p99 / timeout | Load and shed limit | Lease | Evidence sample / window |
|---|---|---|---|---|---|---|---|
| EIP-PERF-QUERY-001 | Authorized Company Brain query | reference | L0 | 3000 / 6000 / 10000 ms | 60/min; 12 in-flight; queue 0/0s | No durable lease (reference path) | 500 / 60 min |
| EIP-PERF-PRG-001 | PR Guardian shadow observation and trusted publication | reference | L1 | 20000 / 45000 / 60000 ms | 12/min; 3 in-flight; queue 50/300s | No durable lease (reference path) | 100 / 10080 min |
| EIP-PERF-OPS-001 | Operational intelligence evidence-to-L2 proposal | reference | L2 | 15000 / 30000 / 45000 ms | 6/min; 2 in-flight; queue 20/180s | No durable lease (reference path) | 50 / 10080 min |
| EIP-PERF-L3-001 | Certified L3 remediation rehearsal | target | L3 | 120000 / 210000 / 240000 ms | 1/min; 1 in-flight; queue 5/900s | 300s; heartbeat 30s; approval outside lease | 30 / 10080 min |
| EIP-PERF-L4-001 | Bounded L4 remediation for a certified scope | target | L4 | 150000 / 270000 / 300000 ms | 1/min; 1 in-flight; queue 3/900s | 360s; heartbeat 30s; approval outside lease | 100 / 43200 min |

| Contract | Step | p95 | p99 | timeout |
|---|---|---:|---:|---:|
| EIP-PERF-QUERY-001 | authenticate-and-authorize | 200 ms | 500 ms | 1000 ms |
| EIP-PERF-QUERY-001 | retrieve-and-ground-or-refuse | 2500 ms | 5000 ms | 8000 ms |
| EIP-PERF-QUERY-001 | render-response | 300 ms | 500 ms | 1000 ms |
| EIP-PERF-PRG-001 | validate-event-and-authorize-context | 500 ms | 1000 ms | 3000 ms |
| EIP-PERF-PRG-001 | collect-diff-and-assess-risk | 12000 ms | 26000 ms | 35000 ms |
| EIP-PERF-PRG-001 | persist-observation-and-artifact | 3000 ms | 7000 ms | 12000 ms |
| EIP-PERF-PRG-001 | trusted-neutral-publication | 4500 ms | 10000 ms | 15000 ms |
| EIP-PERF-OPS-001 | authenticate-and-validate-event | 500 ms | 1000 ms | 3000 ms |
| EIP-PERF-OPS-001 | collect-authorized-evidence | 8000 ms | 15000 ms | 22000 ms |
| EIP-PERF-OPS-001 | correlate-and-build-l2-proposal | 4000 ms | 9000 ms | 12000 ms |
| EIP-PERF-OPS-001 | record-and-return-proposal | 2000 ms | 5000 ms | 8000 ms |
| EIP-PERF-L3-001 | assemble-plan-and-authorized-evidence | 2000 ms | 5000 ms | 10000 ms |
| EIP-PERF-L3-001 | opa-policy-decision | 1000 ms | 3000 ms | 5000 ms |
| EIP-PERF-L3-001 | digital-twin-rehearsal | 45000 ms | 90000 ms | 120000 ms |
| EIP-PERF-L3-001 | bounded-execution | 25000 ms | 50000 ms | 60000 ms |
| EIP-PERF-L3-001 | independent-verification-and-audit | 30000 ms | 60000 ms | 70000 ms |
| EIP-PERF-L4-001 | revalidate-scope-plan-and-error-budget | 3000 ms | 7000 ms | 12000 ms |
| EIP-PERF-L4-001 | opa-policy-and-certificate-check | 1000 ms | 3000 ms | 5000 ms |
| EIP-PERF-L4-001 | digital-twin-or-equivalent-required-rehearsal | 60000 ms | 120000 ms | 150000 ms |
| EIP-PERF-L4-001 | bounded-execution-or-rollback | 35000 ms | 70000 ms | 90000 ms |
| EIP-PERF-L4-001 | independent-verification-and-immutable-audit | 45000 ms | 70000 ms | 90000 ms |
<!-- PERFORMANCE-CONTRACT-TABLE:END -->

The `reference` rows describe current product surfaces that still need a named pilot scope and
measured evidence. The `target` rows specify the requirements before the L3/L4 paths can be
treated as operational candidates; they do not assert that those workflows are deployed.

## Lease boundary

`orchestration.DurableRunner` defaults to a 60-second lease over a local SQLite reference queue.
That value is not a capacity model, is not attached to a managed workflow runtime, and is **not**
an L3/L4 execution setting. The L3/L4 rows require a durable runtime, active lease heartbeats,
and a lease that covers the full active timeout plus a heartbeat interval. A future runtime
binding may not reuse the 60-second default to satisfy these targets.

Changing a target or execution lease requires a retained measurement, owner/SRE review, and an
updated versioned baseline. It must not be changed merely to make a review finding disappear.

## Observation artifact schema

Store one report for one contract, scope, and measurement window in the approved evidence system.
It must contain no request body, source-document content, pull-request diff, credential, or
personal identifier. The minimum shape is:

```json
{
  "contract_id": "EIP-PERF-PRG-001",
  "scope": "owner/repository, integration, region, internal, L1",
  "change": "sha=<git sha> image=<digest> policy=<bundle> prompt=<version>",
  "basis": "measured",
  "source_run_url": "https://approved-evidence.example/runs/123",
  "window": {
    "started_at": "2026-09-01T00:00:00+00:00",
    "ended_at": "2026-09-08T00:00:00+00:00"
  },
  "sample_count": 100,
  "metrics": {
    "p50_latency_ms": 1200,
    "p95_latency_ms": 5000,
    "p99_latency_ms": 8000,
    "max_latency_ms": 12000,
    "success_rate": 0.995,
    "peak_in_flight": 2,
    "peak_queue_depth": 4,
    "peak_queue_age_seconds": 20,
    "rejected_count": 0,
    "unit_cost_usd": 0.03
  },
  "artifacts": ["https://approved-evidence.example/reports/123#sha256:..."],
  "known_limitations": "Integration environment; not a production claim."
}
```

Every observation declares the canonical `contract_id`; requires a timezone-aware window,
sample count, bounded low-cardinality metrics, retained artifact references, and known
limitations. A `measured` observation also requires an HTTPS run URL. The contract declares which
metric names are mandatory for each workflow. L3/L4 reports additionally require audit-write and
independent-verification success rates.

Validate a contract and prevent the rendered table from drifting:

```bash
python scripts/verify_performance_contract.py --check-rendered
```

Validate a real report without writing any repository state:

```bash
python scripts/validate_performance_observation.py \
  --input retained-performance-report.json
```

Exit code `0` from the second command means the artifact is valid and meets its target; `1` means
it is valid but misses one or more targets; `2` means it is malformed. None of those outcomes is
a promotion decision. After independent review, link the retained report from a new immutable
record created with [`scripts/record_evidence.py`](../scripts/record_evidence.py).

## Promotion and recalibration

The target comparison is a necessary input, not a sufficient promotion gate. The evidence record
still needs the precise claim, independent verifier, approval/expiry, artifact digest, and the
decision it supports. Readiness additionally requires the appropriate security, recovery, audit,
and soak evidence in [`PRODUCTION-READINESS.md`](PRODUCTION-READINESS.md).

For a pilot, review p50/p95/p99, maximum latency, success/rejection rates, peak concurrency and
queue pressure, dependency quota behavior, and unit cost weekly. Tighten or relax a target only
with a reasoned change record; never silently normalize failure by rewriting the baseline.
