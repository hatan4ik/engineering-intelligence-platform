# Company Brain Memory Maintenance

| | |
|---|---|
| **Status** | Reference implementation — deterministic review-only planning and outcome correlation, not a scheduled publisher or production workflow |
| **Code** | [`company_brain/maintenance.py`](../company_brain/maintenance.py), [`company_brain/maintenance_outcomes.py`](../company_brain/maintenance_outcomes.py), [`scripts/plan_company_brain_maintenance.py`](../scripts/plan_company_brain_maintenance.py), and [`scripts/validate_company_brain_maintenance_outcome.py`](../scripts/validate_company_brain_maintenance_outcome.py) |
| **Depends on** | [Durable Store Contract](COMPANY-BRAIN-STORE.md) and [Governed Memory Synchronization](COMPANY-BRAIN-MEMORY-SYNC.md) |

## Purpose

Company Brain needs a bounded maintenance loop as well as governed ingestion and retrieval. The
first `dreaming & pruning` slice reads durable organizational memory, identifies reviewable
knowledge-health issues, and produces stable proposals for a human owner. It does **not** change
the source system, tombstone a Company Brain record, publish an issue, or grant action authority.

```text
active tenant-scoped source facts + provenance + owner relationships
  -> deterministic maintenance planner (explicit policy + as-of time)
  -> review-only proposal artifact
  -> explicit human disposition
  -> independent observation of the authoritative source revision
  -> governed ingestion reconciles the resulting source lifecycle change
```

This ordering is intentional: the source system remains authoritative, and the Brain records the
new state only through its existing governed projection path.

An accepted disposition alone is not recorded as a successful maintenance result. The outcome
contract emits `accepted-awaiting-source-observation` until a different identity observes a
changed revision for the exact tenant, source ID, source system, and source record after the
review. `rejected` and `expired` remain explicit non-success outcomes. The validator at
[`scripts/validate_company_brain_maintenance_outcome.py`](../scripts/validate_company_brain_maintenance_outcome.py)
parses bounded proposal/decision/observation artifacts and makes no source-system calls.

## Inputs and detection rules

The v1 policy assesses only active `adr`, `runbook`, and `document` entities. Historical
deployments, incidents, work items, conversations, product findings, and outcomes are not silently
treated as decaying documents.

| Condition | Evidence used | Review-only action |
|---|---|---|
| Stale source | projected `source_updated_at` exceeds the policy threshold | `request-owner-review` |
| Missing accountable owner | active `owner --owns--> artifact` relationship is absent | `assign-accountable-owner` |
| Conflicting active revision | same source type and normalized title have different active source revisions | `resolve-conflicting-active-revisions` |
| Unknown source freshness | `source_updated_at` is absent or malformed | `repair-source-freshness-metadata` |

`source_updated_at` is projected from `KnowledgeDocument.updated_at`; it is deliberately distinct
from the SQLite record's `updated_at`, which says when the Brain projection was written. The
planner never uses projection-write time as a false freshness signal. A missing source timestamp
creates an explicit repair proposal and suppresses only the stale-age calculation until a governed
source replay supplies the timestamp.

Ownership comes only from an active canonical `owns` relationship whose source is an `owner`
entity. The planner does not infer ownership from a title, service name, model response, or an
arbitrary metadata field. Tombstoned entities and relationships are excluded. A conflict is a
request for review, not evidence that either source is wrong.

## Proposal contract and safety boundary

Each proposal carries the tenant, durable source ID, source system/record/revision, source record
version, condition, severity, recommendation, and policy version. Its ID is a SHA-256 digest of
those semantic inputs, so the same source version and policy produce the same proposal ID across
repeat runs. The explicit `as_of` value makes the finding reason reproducible; it is not folded
into the ID to avoid creating a new ticket every day for the same unresolved record.

The proposal payload intentionally excludes source bodies, evidence citations, ACLs, credentials,
and executable instructions. Every proposal has `requires_human_review: true`. The planner has a
narrow read port containing only `list_entities` and `list_relationships`; it has no write,
publisher, workflow, or remediation dependency.

`SqliteCompanyBrainStore.open_read_only()` opens an existing reference database with SQLite
`mode=ro` and `query_only=ON`. It does not initialize a schema or create a new database. The CLI
also refuses an `--output` path equal to `--database`.

## Reference operation

Run this only against an existing local/reference database and write the review artifact somewhere
other than that database:

```bash
EIP_CONTROL_PLANE_MODE=reference \
  python scripts/plan_company_brain_maintenance.py \
  --database /path/to/company-brain.db \
  --tenant tenant-acme \
  --as-of 2026-08-30T12:00:00Z \
  --output /tmp/company-brain-maintenance.json
```

An empty proposal list is a valid successful result. The command is not a scheduler and does not
prove a live source sync, ticket integration, owner response, or freshness SLO.

## Remaining work

1. Add an approved, source-specific publisher that routes a proposal to a human owner without
   changing source truth directly.
2. Connect explicit reviewer dispositions and independent source observations to an approved,
   source-specific system of record. The checked-in contract validates their shape and correlation,
   but no external integration or retained outcome evidence exists yet.
3. Define freshness/owner-response SLOs and retain pilot evidence before claiming operational
   effectiveness.
4. Add policy-reviewed eligibility for other knowledge types only when their lifecycle semantics
   justify expiry or maintenance.
