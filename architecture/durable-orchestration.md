# Durable Orchestration

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

The current integration path is **Temporal Server on private AKS with private Azure PostgreSQL
Flexible Server**; see [ADR-001](ADR-001-temporal-control-plane.md). The repository now includes
a pinned, fail-closed Temporal Helm wrapper, Terraform declarations for the PostgreSQL foundation,
and runtime guards that prevent local SQLite components from being used when
`EIP_CONTROL_PLANE_MODE=temporal`.

This is not yet a Temporal worker implementation, a deployed service, or production evidence.
The worker adapter, private secret delivery, schema-migration runbook, backup/restore drill, and
immutable audit export remain required before a remediation workflow can leave reference mode.
