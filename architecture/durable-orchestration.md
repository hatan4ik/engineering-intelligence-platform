# Durable Orchestration

| | |
|---|---|
| **Classification** | Current design |
| **Owner** | Platform Engineering |
| **Reviewed** | 2026-08-26 |
| **Assertions are** | design; the SQLite queue is reference-only, Temporal runs an evidence-only worker |
| **Authoritative current state** | [`CURRENT-POSITION.md`](../docs/CURRENT-POSITION.md) |


Workflow state and execution scheduling are separate concerns. `WorkflowRecord` is authoritative business/control-plane state; the durable job queue drives resumable work.

## Semantics

`event -> workflow record -> durable job -> leased worker -> handler -> complete/retry/DLQ`

- Job IDs are idempotency keys; duplicate enqueue is ignored.
- Claims use a time-bounded lease, not permanent ownership.
- A crashed worker's job becomes claimable after lease expiry.
- Failed handlers use bounded exponential backoff.
- `max_attempts` moves poison jobs to `dead_letter`.
- Unknown job kinds fail closed; they are never silently completed.
- Completion is durable and prevents normal reprocessing.

## Production boundary: Distributed Workflow Engine

While `SqliteJobQueue` or basic message brokers might suffice for a prototype, a mature FAANG-level self-healing platform is fundamentally a distributed state machine. Custom lease-based queues lead to race conditions, zombie workers, and corrupted state during infrastructure failures.

The production architecture mandates a **Durable Execution Engine (e.g., Temporal, Cadence, or AWS Step Functions)** to manage control-plane workflows. This guarantees:

1. **Native Crash Recovery**: If a worker node dies mid-remediation (e.g., while draining a node), the workflow engine flawlessly resumes the execution state on a new worker without race conditions.
2. **Long-Running Awaits**: Workflows can yield (sleep) for hours waiting for a node to drain or an approval to be granted without consuming compute resources.
3. **Strict Consistency**: Eliminates the "split-brain" worker problem common in lease-based systems.
4. **Built-In Retries and DLQ**: Exponential backoffs and dead-letter queues are handled natively by the engine rather than custom application logic.
5. **Observability**: Full visual timelines of exactly where a self-healing process is blocked or has failed.

Handlers remain typed code. Free-form model output does not become an executable job kind.

## Chosen integration path

The target integration path is **Temporal Server on private AKS with private Azure PostgreSQL
Flexible Server**; see [ADR-001](adr/001-temporal-control-plane.md). The repository now includes
a pinned, fail-closed Temporal Helm wrapper, Terraform declarations for the PostgreSQL foundation,
an mTLS-only evidence-worker deployment boundary, and runtime guards that prevent local SQLite
components from being used when `EIP_CONTROL_PLANE_MODE=temporal`. Operating or validating that
target environment is deferred while product implementation continues.

The registered `eip.control-plane-evidence.v1` worker is non-consequential: it proves only durable
scheduling and must not mutate state or execute an agent workflow. It is not a deployed service or
production evidence. It uses only Temporal/mTLS configuration; it has no Azure Workload Identity
or Temporal/PostgreSQL configuration. The authoritative-state/audit activity bridge will introduce its
own least-privilege identity, state and audit dependencies, and the required idempotency, recovery,
and audit-failure semantics before a remediation workflow can leave reference mode. See
[`../docs/TEMPORAL-WORKER-RUNBOOK.md`](../docs/TEMPORAL-WORKER-RUNBOOK.md).
