# L3 Rehearsal Runbook

| | |
|---|---|
| **Classification** | Current implementation state |
| **Owner** | Platform Engineering |
| **Status** | Runner implemented; no exercise in this repository has been run against a real cluster |
| **Scope** | The certification exercise suite and its two runners; not a certification and not an authorization |
| **Related** | [`PRODUCTION-EVIDENCE.md`](PRODUCTION-EVIDENCE.md), [`PRODUCTION-PROOF-PLAN.md`](PRODUCTION-PROOF-PLAN.md), [`../architecture/l4-certification.md`](../architecture/l4-certification.md) |

## What this runner does

`scripts/run_l3_exercises.py` runs every `resilience.exercises.ExerciseKind` for one
`--service --environment --runbook` scope. Each exercise provisions the digital twin's ephemeral
sandbox namespace, drives `remediation.executor.execute_control_loop` through it, and records an
`ExerciseResult`. The suite covers the positive path and the fail-closed paths: verification
failure, rollback, kill switch, policy outage, audit outage, and an exhausted error budget.

```bash
PYTHONPATH=. python scripts/run_l3_exercises.py \
  --service payments --environment prod --runbook aks.restart.crashloop
```

It writes `l3-exercises-<scope-hash>.json` next to the invocation (or in `--output-dir`), where
the scope hash is a digest of `service|environment|runbook`.

## The two runners

| | `--runner simulated` (default) | `--runner kubectl` |
|---|---|---|
| Cluster | An in-memory model answering the fixed kubectl argv | The real cluster in `KUBECONFIG` |
| Processes started | None | `kubectl` |
| Policy | `LocalReferenceEvaluator` unless `--opa-endpoint` is given | OPA at `--opa-endpoint` (required) |
| `evidence_grade` | `rehearsal` | `cluster-exercise` |
| `production_evidence` | `false` | `true` |
| Certification assessment in the output | Always `null` | `resilience.certification.build_certification_report` |

`--runner kubectl` fails closed at startup and lists what is missing: `KUBECONFIG`, `kubectl` on
PATH, and `--opa-endpoint`. There is no implicit local fallback for a run that claims real
evidence.

## Simulated results are a rehearsal, not certification

A simulated run proves that the control loop behaves as designed against a model of a cluster. It
proves nothing about a real cluster, a real policy bundle, a real audit sink, or a real workload.
Every simulated record carries `"evidence_grade": "rehearsal"`, the report carries
`"production_evidence": false` and a disclaimer, and the runner deliberately emits no certification
assessment for a simulated run — grading a rehearsal would invite it being read as certification.

Simulated output must never be filed as an evidence record under
[`PRODUCTION-EVIDENCE.md`](PRODUCTION-EVIDENCE.md) or cited in an L3 or L4 promotion decision.

## What a cluster run is, and is not

A `--runner kubectl` run is an *input* to certification. It is not a certification. The
`certification_assessment` block it emits reports `security_reviewed: false` and
`verification_independent: false` unconditionally, because neither is something a runner can
observe — both are human review outcomes. An L3 or L4 decision additionally requires retained,
independently reviewed evidence for the exact scope, per
[`../architecture/l4-certification.md`](../architecture/l4-certification.md).

A failing exercise is reported as failing. A runbook with no usable rollback path fails its
rollback exercise; that is the correct result for that runbook, not a defect in the runner.

## Related runners

- `scripts/run_soak.py` evaluates a continuous-operation window from a JSONL telemetry export
  against the 168-hour requirement in [`PRODUCTION-PROOF-PLAN.md`](PRODUCTION-PROOF-PLAN.md). The
  export shape is documented in `validation/soak.py`. It exits 1 when the longest continuous window
  is short of the requirement.
- `scripts/production_readiness_report.py` evaluates the fail-closed readiness gate over an
  evidence directory and names every missing required key. An empty or absent directory means every
  key is missing, which is what *not proven* looks like.
