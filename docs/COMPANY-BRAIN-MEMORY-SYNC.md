# Company Brain Governed Memory Synchronization

| | |
|---|---|
| **Classification** | Reference contract — connector lifecycle, not a deployed data plane |
| **Code** | [`company_brain/memory.py`](../company_brain/memory.py) |
| **Depends on** | [Durable Store Contract](COMPANY-BRAIN-STORE.md) |

## Purpose

The Company Brain must be fed by governed source lifecycle, not a one-time index build.
`CompanyBrainMemoryProjector` writes authorized repository and knowledge-document changes through
the durable Company Brain contract. Each projector instance is bound to one explicit `tenant_id`;
the tenant is never inferred from an untrusted webhook or document payload.

## Write-through flow

```text
authorized source event or reconciliation manifest
  -> retrieval index write/delete succeeds
  -> Company Brain projection + membership journal
  -> source catalog advances
```

`IngestionPipeline` follows this order for repository changes. If the Brain projection fails, the
source catalog does not advance, so the event ledger or reconciliation loop can retry it. The
existing in-memory projector remains available for deterministic reference tests, but the durable
projector is the governed path.

`KnowledgePipeline` uses the same projector after its index write. It also invokes the projector
when the index reports an unchanged revision, allowing a retry to repair a previously missing Brain
projection without re-indexing source content.

## Source membership rules

The SQLite projection journal keeps only compact source metadata: tenant, source key, fingerprint,
provenance, projected record IDs, and edge memberships. It does not store source body content.

| Lifecycle event | Company Brain effect |
|---|---|
| First upsert | Create/refresh source evidence, source-owned artifact facts, and their relationships |
| Same fingerprint / replay | No durable write; returns a duplicate receipt |
| ACL, content, or revision change | Refresh the evidence pointer and recompute memberships; obsolete source evidence is tombstoned |
| Source absent from complete reconciliation manifest | Tombstone the source’s evidence and source-owned artifact facts; retain shared repository/service/owner facts |
| Shared edge loses one source | Retain the edge with evidence from remaining active source memberships |
| Reused event ID with different state/content | Reject as a replay conflict |

An evidence pointer is ACL-bearing. Therefore an ACL reconciliation updates the Company Brain
evidence visible to a principal; old evidence is tombstoned rather than silently retained in an
active context.

## Failure boundary

This reference implementation has two local SQLite databases: the Company Brain store and the
projection-membership journal. It is state-convergent under retry, but it is not a distributed
exactly-once transaction. A process failure between them is repaired by replay/reconciliation; the
catalog ordering above prevents that partial state from being marked as fully applied.

A managed implementation must make this boundary durable with an outbox, transactional write
model, or equivalent replay receipt. It must preserve the same tenant isolation, ACL, tombstone,
provenance, and relationship-membership semantics.

## Explicit non-goals

- No Azure deployment, connector credential, or production source claim.
- No flattening of source authorization into the Company Brain.
- No action authority: a synchronized fact, edge, or document cannot approve a PR or execute a
  runbook.

The synchronized record is then consumed through the [qualified world-model query layer](COMPANY-BRAIN-WORLD-MODEL.md),
which applies source trust, freshness, conflict, and request-principal checks before a graph edge
can influence a product workflow.
