# Temporal Worker Implementation Boundary

| | |
|---|---|
| **Classification** | Current implementation state |
| **Status** | Evidence-worker boundary implemented; undeployed, unoperated, and not production-proven |
| **Scope** | L0 durable-scheduling capability only; no business state, audit export, product action, or remediation mutation |
| **Pipeline position** | Evidence-worker slice complete; state/audit activity bridge implemented but deliberately unregistered |
| **Decision** | [`../architecture/adr/001-temporal-control-plane.md`](../architecture/adr/001-temporal-control-plane.md) |
| **Product roadmap** | [`../roadmap/technical-roadmap-24-months.md`](../roadmap/technical-roadmap-24-months.md) |

This file intentionally keeps its historical name so existing links remain valid. It is an
implementation-boundary document, not an operating runbook: there is no Temporal environment to
operate in the active product-build stage.

## Implemented boundary

`orchestration.temporal_worker` starts only when `EIP_CONTROL_PLANE_MODE=temporal` and registers
exactly one deterministic workflow: `eip.control-plane-evidence.v1`.

The workflow returns its bounded request/correlation identifiers and Temporal workflow ID with
`mutation_performed: false`. It does not call Cosmos, export an audit record, read a Kubernetes
API, run a remediation, approve/block a PR, or carry product authority. The purpose is to keep
the Temporal scheduling and mTLS adapter narrow and testable without claiming that a durable
business/control plane exists.

## Current configuration contract

The evidence worker accepts only the dependencies it consumes. There is no local default or
fallback.

| Input | Requirement |
|---|---|
| Temporal endpoint, namespace, task queue | Explicit private `host:port`, dedicated namespace and queue |
| mTLS server name and Secret | Existing approved Secret; no PEM material in Helm values or environment variables |
| `ca.crt`, `tls.crt`, `tls.key` | Mounted Secret files, read from fixed paths only |
| Image | Digest-pinned image; no mutable tag |

`EIP_COSMOS_ENDPOINT`, state-container settings, and immutable-audit destination settings are
not evidence-worker configuration. They will be introduced only with a separate registered
activity worker that consumes them.

## Deployment boundary

`helm/eip` renders this worker only when `temporalWorker.enabled=true`; it is `false` by default.
The rendered workload has at least two replicas, a disruption budget, non-root/read-only
filesystem settings, a writable `emptyDir` only for `/tmp`, and a dedicated ServiceAccount with
Kubernetes API token mounting disabled.

The evidence worker deliberately has no Azure Workload Identity, Cosmos RBAC, or audit-store
credential. Granting those permissions before an activity consumes them would expand the trust
boundary without product value. The state/audit bridge must receive its own least-privilege
identity and configuration surface; it must not reuse this worker's identity merely for
convenience.

Source-only template checks remain valid and do not contact Azure:

```bash
helm lint helm/eip --values helm/eip/values.ci.yaml
helm template eip helm/eip --values helm/eip/values.ci.yaml
```

The CI fixture uses `example.invalid` identifiers and an all-zero image digest; it cannot identify
or deploy a real environment.

## Explicitly out of scope now

No Azure, AKS, Temporal-server, private-runner, certificate, DNS, workflow-execution, or
production-proof exercise is part of this stage. The deferred helper
`validation.temporal_control_plane_probe` is retained for a later approved operational-validation
plan; this document deliberately provides no execution procedure for it.

[`PRODUCTION-PROOF-PLAN.md`](PRODUCTION-PROOF-PLAN.md) and
[`INTEGRATION-PROOF-RUNBOOK.md`](INTEGRATION-PROOF-RUNBOOK.md) describe a future validation track.
They do not authorize current work.

## Implemented but unregistered: state and audit activity bridge

[`../architecture/authoritative-state.md`](../architecture/authoritative-state.md) now defines a
schema-versioned lifecycle event and an unregistered
`eip.persist-workflow-lifecycle.v1` activity boundary. It persists an optimistic-concurrency
state transition with an idempotency receipt, then exports a deterministic audit event. On audit
failure it returns an error; a retry reuses the receipt and must not reapply state.

The reference implementation covers canonical IDs/scope/plan binding, legal lifecycle transitions,
duplicate delivery, stale writes, audit outage/retry, worker-restart recovery, and terminal
cancellation. It uses a local hash-chained audit log in CI and a same-workflow-partition Cosmos
transactional receipt contract. It does not constitute immutable external retention.

## Remaining before any activity registration

The next design/implementation decision is a remote immutable/WORM audit exporter, including its
retention policy and independently scoped workload identity. Only then can a separate worker take
state/audit configuration; it must not reuse the evidence worker identity. Managed schema
migration, backup/restore, Temporal worker failover, and independent operational validation remain
separately governed future work. This evidence worker must not be repurposed as a generic task
executor in the meantime.
