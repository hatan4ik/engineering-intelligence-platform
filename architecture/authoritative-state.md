# Authoritative State and Audit Boundary

| | |
|---|---|
| **Classification** | Current design and reference implementation state |
| **Status** | Lifecycle state/audit bridge implemented and unregistered; no managed environment, remote immutable sink, or production proof |
| **Scope** | Canonical workflow transitions, durable idempotency receipts, compare-and-swap, and fail-closed audit export semantics |
| **Implementation evidence** | `state/lifecycle.py`, `state/store.py`, `state/temporal_store.py`, `orchestration/control_plane_activities.py`, and `tests/test_control_plane_activity_bridge.py` |
| **Roadmap** | [`../roadmap/technical-roadmap-24-months.md`](../roadmap/technical-roadmap-24-months.md) |

The Engineering Intelligence Platform separates **authoritative operational state** from
retrieval projections. Azure AI Search is never the system of record for services, workflows,
approvals, or audit history; its indexes are rebuildable projections.

The target ownership split among Company Brain state, Azure AI Search, Temporal/PostgreSQL,
and immutable audit export — including recovery responsibilities — is fixed in
[ADR-003](adr/003-company-brain-runtime-topology-and-recovery.md). This repository's adapter
interfaces do not prove that the target stores or recovery procedures are deployed.

## Canonical lifecycle contract

`WorkflowLifecycleEvent` is schema-versioned and contains the event and idempotency IDs,
workflow/correlation/causation IDs, tenant and service scope, actor, action, prior and next status,
expected optimistic version, plan hash, consequential flag, canonical JSON attributes, and a
timezone-qualified occurrence time.

Only explicit legal transitions are accepted. New workflows begin at `received`; cancellation is
explicit and terminal; terminal workflows cannot resume. A timeout must be represented by a named
lifecycle event to `failed` or `escalated`, never by silently continuing execution.

## Atomic state and retry semantics

`SqliteStateStore.apply_workflow_event()` stores the workflow update and a transition receipt in
one transaction. `TemporalStateStore` uses Temporal's native workflow event history
batch for the equivalent state document and receipt. Both enforce application-level expected
versions; the Temporal path guarantees this via workflow determinism.

The receipt binds the workflow ID, event ID, idempotency key, canonical event fingerprint, and
resulting workflow snapshot. A duplicate delivery returns the original snapshot with
`replayed=true`; it does not increment the workflow version. Reusing an event or idempotency key
with different content fails closed.

This covers activity retry, worker restart, and response-loss replay. It is not a backup/restore
implementation: managed backup, restore, retention, and regional-failure procedures remain a
separate operational delivery track.

## Audit export boundary

`ControlPlaneActivityBridge.persist_workflow_lifecycle()` first writes the authoritative state
transition, then exports a deterministic audit event derived from the same lifecycle event. If the
audit export fails, the activity raises `AuditExportFailure`; the workflow must not move to a
consequential next step. On retry, the state receipt prevents a second transition and the same
audit event is retried.

`SqliteAuditLog` is a deterministic local reference implementation: it uses a hash chain and
idempotent event IDs for test/CI. It is **not** immutable external storage. A managed exporter must
preserve this event-ID idempotency contract and provide approved WORM/immutable retention before
any consequential workflow is registered or operated.

## Deliberately unregistered boundary

The current Temporal worker registers only `eip.control-plane-evidence.v1`. It does not register
`eip.persist-workflow-lifecycle.v1`, and it has no state or audit credentials. Registering the
activity requires a separate worker identity, remote-state configuration, immutable-exporter
choice, retention policy, and independent operational validation. See
[`../docs/TEMPORAL-WORKER-RUNBOOK.md`](../docs/TEMPORAL-WORKER-RUNBOOK.md).

## Deterministic guarantees exercised in CI

- duplicate delivery creates one workflow version and one audit event;
- stale optimistic versions produce no state or audit write;
- an audit outage retains state but returns failure; a restarted worker retries the audit without
  replaying state;
- cancellation is explicit and terminal; and
- the Temporal adapter natively records this in the event history.

No item above is production evidence. Private connectivity, identity/RBAC, WORM retention,
backup/restore, Temporal worker failover, and audit-export availability are intentionally outside
this source-only stage.
