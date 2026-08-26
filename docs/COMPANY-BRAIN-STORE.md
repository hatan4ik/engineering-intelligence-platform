# Company Brain Durable Store Contract

| | |
|---|---|
| **Status** | Local/reference implementation only — not a deployed production data plane |
| **Code** | [`company_brain/store.py`](../company_brain/store.py) |
| **Purpose** | Preserve Company Brain facts, evidence pointers, and relationships as governed records rather than search-index documents |

## Guarantees in the reference contract

`SqliteCompanyBrainStore` is a deterministic local implementation of the durable-system-of-record
boundary. It exists to make required behavior executable before a managed data plane is selected.

| Concern | Contract |
|---|---|
| Tenant isolation | Every read and write requires a `tenant_id`; entity, evidence, relationship, and audit keys are tenant-scoped |
| Source provenance | Every write supplies source system, source record ID, revision, observed time, and optional event ID |
| Concurrency | Writes use a SQLite `BEGIN IMMEDIATE` transaction and optional compare-and-swap `expected_version` |
| Evidence safety | Evidence records contain citations, revision, source kind, and ACL metadata only — never source body content |
| Relationship safety | Both endpoints and every referenced evidence pointer must be active in the same tenant before an edge is accepted |
| Deletion | Entity, evidence, and relationship deletion creates a tombstone with reason and lifecycle audit event; normal reads omit it and no hard-delete API exists |
| Retention | Retention cannot be shortened and legal hold cannot be removed through an ordinary update; legal-hold records cannot be tombstoned |
| Auditability | Create, update, and tombstone events keep the record key, version, timestamp, and source provenance without duplicating source content |

The store can rebuild an active `CompanyBrain` snapshot for a read-only product adapter. This is a
read model only: it does not grant authorization, approve a change, trigger a workflow, or execute
a remediation.

## Boundaries and next work

- SQLite is explicitly reference-only and refuses construction when the repository is configured for
  the Temporal runtime profile. A managed production implementation must preserve this contract;
  neither an embedding index nor a vector database may become the authoritative record.
- Evidence deletion atomically tombstones its structural graph entity, so a reconstructed snapshot
  cannot retain an orphaned active evidence pointer. A tombstone provides access deletion and
  reconciliation evidence. Legal/compliance-led physical
  purge must be designed with a source-system retention schedule and immutable-audit policy; it is
  intentionally not hidden behind a local convenience method.
- Repository and knowledge-document lifecycle now write through this contract via the
  [governed-memory synchronization boundary](COMPANY-BRAIN-MEMORY-SYNC.md). Connector scheduling,
  managed outbox/receipt storage, broader source coverage, and graph confidence/freshness remain
  separate increments.
