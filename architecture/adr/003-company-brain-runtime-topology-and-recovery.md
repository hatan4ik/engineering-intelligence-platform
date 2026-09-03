# ADR-003: Company Brain systems of record and recovery boundaries

| | |
|---|---|
| **Classification** | Accepted architecture decision — source-only design, not a deployment record |
| **Owner** | Platform Engineering |
| **Decision date** | 2026-08-30 |
| **Scope** | Company Brain data ownership, durable runtime topology, and recovery obligations |
| **Related decisions** | [ADR-001](001-temporal-control-plane.md), [authoritative state](../authoritative-state.md), [runtime capability contract](../../docs/RUNTIME-CAPABILITY-CONTRACT.md) |
| **Authoritative current state** | [`../../docs/CURRENT-POSITION.md`](../../docs/CURRENT-POSITION.md) |

## Context

The Company Brain needs to remember authorized organizational facts, show the
provenance behind a finding, retain durable workflow decisions, and recover
without promoting a rebuilt search index or a Temporal visibility record into
the source of truth. Those concerns have different consistency, retention,
and recovery properties.

The repository has useful reference adapters today, but no deployed topology:

- Terraform declares a private AKS foundation, Azure AI Search/OpenAI/Key
  Vault, and a private PostgreSQL foundation for Temporal;
- it does **not** declare Cosmos DB, Service Bus, a `helm_release`, or a
  Temporal Server instance;
- the Temporal Helm wrapper and mTLS evidence worker are source/deployment
  boundaries, not a running control plane; and
- the previously dormant Service Bus queue was deliberately removed. No broker
  can be reintroduced merely because a target diagram needs one.

Without an explicit ownership decision, an index, a task queue, or an audit
projection could accidentally be treated as recoverable business state.

## Decision

Use a separated, recoverable Company Brain topology:

```text
Authorized sources / webhook events
              |
              v
    API and ingestion boundary (auth, schema, correlation)
              |
       +------+------------------+
       |                         |
       v                         v
Company Brain state         Retrieval projection
facts/findings/outcomes     Azure AI Search
Cosmos DB (target)          rebuildable from authorized sources
       |
       +------------------+
                          v
                 Temporal control plane
                 Temporal Server + private PostgreSQL
                          |
              policy / approval / activity adapters
                          |
                          v
               immutable audit export (target)
```

1. **Company Brain state is the application system of record.** The target
   implementation uses Cosmos DB for canonical facts, findings, outcomes,
   provenance, workflow receipts, and application audit identity. Each record
   is scoped by tenant/service and protected by optimistic concurrency and
   idempotency keys. The `state/` interfaces, not a provider SDK, define this
   contract.
2. **Azure AI Search is a rebuildable retrieval projection.** It may hold
   authorized, ACL-trimmed document projections and embeddings. It is never
   authoritative for facts, approvals, workflow state, or audit history.
   Search loss is recovered by reconciling authorized source/state records,
   not by accepting index contents as truth.
3. **Temporal owns workflow execution history, not Company Brain state.**
   Temporal Server persists its own history and visibility stores in separate
   PostgreSQL databases as defined by ADR-001. A Temporal replay or visibility
   query cannot replace a Company Brain lifecycle receipt, finding, approval,
   or audit record.
4. **Audit export is a separate immutable evidence plane.** A local hash chain
   and Cosmos audit adapter are reference behavior only. Before consequential
   workflows are registered, an approved immutable/WORM export and retention
   policy must preserve event IDs, hashes, correlation IDs, and access control.
5. **A broker is a transport, never the authority.** Direct webhook handling
   and Temporal scheduling are the current paths. Service Bus or another
   broker may be proposed only with a typed port, an owning caller,
   idempotency/replay/DLQ semantics, and a dedicated ADR/PR. It must not become
   a second workflow state machine.

## Recovery model

| Failure boundary | Authoritative data | Safe recovery rule | Required evidence before operation |
|---|---|---|---|
| API/ingestion process | None; process is stateless | Restart or replace after configuration validation; duplicate events rely on idempotency receipts | health, auth, and duplicate-event exercises |
| Azure AI Search projection | Rebuildable projection | Pause affected retrieval; rebuild/reconcile from authorized sources and Company Brain records; never synthesize a guessed answer from missing evidence | ACL/deletion/rebuild reconciliation record |
| Cosmos Company Brain state | Canonical application records | Restore only through an approved point-in-time/backup procedure, then reconcile receipts/projections before reopening workflows | backup/restore drill, RPO/RTO result, integrity reconciliation |
| Temporal/PostgreSQL | Temporal history and visibility | Recover server/history independently; workers resume only after TLS, schema, and application-state/audit compatibility checks | PostgreSQL restore, worker-loss, and workflow-replay drills |
| OPA policy | Authorization decision | Fail closed on unavailable, invalid, or version-mismatched policy; no local permissive fallback in a consequential runtime | policy-outage and bundle-version exercise |
| Audit export | Immutable evidence | Stop consequential progression if export fails; retry the same deterministic event only after the exporter recovers | audit-outage/replay and retention-access evidence |
| Execution adapter | External mutation target | Verify independently; roll back or escalate on failed verification; never retry an unknown mutation automatically | scoped rollback and verification exercise |

No RPO, RTO, availability target, or backup interval is set by this ADR. Those
numbers require a named environment, workload estimate, data classification,
and retained recovery exercise; until then they are deliberately unproven.

## Security and privacy impact

- Tenant, repository, service, and environment scope travel with canonical
  records and provenance. Retrieval ACLs constrain projections; they do not
  substitute for state authorization.
- Private connectivity, workload identity, encryption, audit access, retention,
  legal hold, deletion, and residency are mandatory deployment controls, not
  inferred from provider names in source code.
- Restore paths are privileged operations. They must be separately authorized,
  audited, and tested against least-privilege identities.

## Reliability and rollback impact

- Each data plane has an explicit source of truth and recovery owner; recovery
  never asks a model to reconstruct lost state.
- Rebuildable projections make index corruption/replacement reversible, while
  immutable audit and canonical state make consequential decisions traceable.
- The platform must remain at L0–L2/reference behavior until the state, audit,
  Temporal, policy, and execution recovery evidence in the table exists for a
  named scope.

## FinOps impact

Separate stores prevent accidental retention of all raw knowledge in every
plane. Capacity, backup retention, Search replicas, Temporal history growth,
and audit WORM retention require a cost model before deployment. A rebuild
operation is a metered workload and must have an operator-approved budget.

## Alternatives considered

| Alternative | Decision |
|---|---|
| Treat Azure AI Search as the Company Brain database | Rejected: retrieval indexes are lossy/rebuildable and cannot authoritatively represent approvals, lifecycle receipts, or audit history. |
| Treat Temporal visibility/history as application state | Rejected: it couples domain records to execution implementation and prevents independent recovery/governance. |
| Reintroduce Service Bus as the default workflow authority | Rejected: a transport alone does not provide the typed long-running workflow, compensation, and state semantics required here. |
| Keep SQLite as the distributed durable runtime | Rejected: useful local/reference semantics, but not a multi-worker production system of record. |
| Combine Company Brain state and immutable audit into one unqualified store | Rejected: audit immutability, retention, access, and recovery requirements need independent controls. |

## Consequences

- Future infrastructure work must explicitly add the target Cosmos, Temporal
  Server, audit-export, identity, network, and recovery resources. A Terraform
  declaration is still not deployment evidence.
- Product teams integrate through Company Brain contracts (`Evidence`,
  `Finding`, `Outcome`, provenance) and must not create competing product-local
  systems of record.
- New queues, caches, or projections require declared ownership, replay/DLQ
  behavior, data-classification/retention rules, and a recovery path before
  they are enabled for real data.

## Evidence that can cause reconsideration

Revisit this decision only with retained evidence showing that a different
store or workflow engine meets the same ownership, tenancy, authorization,
idempotency, recovery, immutable-audit, cost, and operational requirements for
a named Company Brain scope.
