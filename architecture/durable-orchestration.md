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

## Production boundary

`SqliteJobQueue` is the deterministic local/CI implementation. A production backend may use Azure Service Bus, PostgreSQL, or another durable queue, but must preserve:

1. idempotent enqueue;
2. exclusive/time-bounded claim semantics;
3. delivery attempt tracking;
4. bounded retries and DLQ;
5. workflow/correlation identity propagation;
6. observable lease age, queue age and failure counts.

Handlers remain typed code. Free-form model output does not become an executable job kind.
