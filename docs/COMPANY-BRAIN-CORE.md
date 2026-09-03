# Company Brain Core v1

| | |
|---|---|
| **Classification** | Reference contract — canonical model and projections, not a deployed system of record |
| **Owner** | Engineering Intelligence lead + Platform Engineering |
| **Product thesis** | Company Brain: governed organizational memory, world model, reasoning, and controlled action |

## Purpose

Company Brain Core is the shared substrate for PR Guardian, Architecture Guard, incident
intelligence, deployment intelligence, and future remediation workflows. It makes the company’s
operating knowledge explicit without treating a model output, graph edge, or document as action
authority.

The core code lives in [`company_brain/`](../company_brain/). It stores normalized facts,
relationships, and minimal evidence pointers. It intentionally does not store source document
content, execute a runbook, or authorize a merge/deployment.

## Canonical model

| Layer | Records | Rule |
|---|---|---|
| Entities | repository, service, team/owner, ADR, change, deployment, incident, runbook, work item, document, conversation | Every entity has a stable type, identifier, label, and deterministic metadata |
| Relationships | `owns`, `depends_on`, `changed_by`, `caused`, `resolved_by`, `governed_by`, `belongs_to`, `has_evidence` | Endpoints and referenced evidence must exist before a relationship is accepted |
| Evidence | citation, revision, source kind, group/user ACL | Evidence is a pointer only and is fail-closed when the requesting identity has no matching ACL |
| Product context | changed services, blast radius, owners, authorized evidence, limitations | Missing, out-of-scope, or unauthorized evidence is reported as a limitation, never silently treated as safe |

## Governed projection

[`CompanyBrainProjector`](../company_brain/projector.py) projects two existing source contracts:

1. An authorized [`FileChange`](../ingestion/models.py) creates repository, change, service, and
   owner facts, with provenance-backed `changed_by`, `belongs_to`, `owns`, and `has_evidence`
   edges.
2. A governed [`KnowledgeDocument`](../ingestion/documents.py) creates ADR, runbook, incident,
   deployment, work-item, document, or conversation facts. An ADR may govern its named service.
   Causal and resolution edges are added only from explicit source metadata; they are never
   inferred from prose.

The core’s in-memory model remains the deterministic projection target. A tenant-isolated
[`SqliteCompanyBrainStore`](COMPANY-BRAIN-STORE.md) now provides the local/reference durable
system-of-record contract: versioned facts, source provenance, retention metadata, legal-hold
protection, tombstone deletion, and an append-only lifecycle trail. A managed implementation must
preserve those semantics; a retrieval or vector index cannot become the authoritative record.

`IngestionPipeline` now accepts an optional `CompanyBrainProjector`. This keeps existing ingestion
callers backward compatible while allowing a governed file change to update the retrieval index,
source catalog, and Company Brain projection only after the index write succeeds.

For durable organizational memory, `IngestionPipeline` and `KnowledgePipeline` also accept an
optional [`CompanyBrainMemoryProjector`](COMPANY-BRAIN-MEMORY-SYNC.md). It binds a connector to an
explicit tenant, journals that source's graph memberships, rejects conflicting event replay, and
propagates ACL changes and source deletion as durable evidence/relationship tombstones. The source
catalog advances only after this projection succeeds, leaving failed projection work replayable.

[`CompanyBrainWorldModel`](COMPANY-BRAIN-WORLD-MODEL.md) is the next read-only layer over durable
records. It qualifies entities and relationships with source trust, freshness, and requesting-user
authorization before calculating repository scope, blast radius, or ownership. Stale,
low-confidence, unauthorized, or directly conflicting links become explicit limitations rather
than hidden decision inputs.

[`Company Brain Memory Maintenance`](COMPANY-BRAIN-MAINTENANCE.md) adds the first bounded
`dreaming & pruning` loop over this durable memory. It derives tenant-scoped, deterministic,
human-review-only proposals for stale, ownerless, conflicting, or freshness-unknown ADRs,
runbooks, and documents. It reads the original source timestamp and canonical ownership edge; it
does not use projection-write time as a freshness proxy or mutate a source, ticket, or Brain fact.

## Safe product use

[`PRGuardianWorldModelAdapter`](../product/pr_guardian/company_brain.py) now converts the durable,
qualified context into the PR Guardian service graph and evidence contract. It is read-only:

- authorized evidence becomes a cited `EvidenceBundle`;
- inaccessible evidence is omitted and produces a limitation;
- the service/dependency graph calculates deterministic blast radius; and
- no adapter result can approve, block, merge, deploy, or change OPA policy.

This is the integration pattern for subsequent Company Brain products: consume a constrained,
authorized context; emit a reviewable outcome; then return explicit feedback and independently
correlated outcomes to governed organizational memory.

[`company_brain/product_contracts.py`](../company_brain/product_contracts.py) is the small,
product-neutral Evidence / Finding / Outcome / provenance vocabulary. PR Guardian translates its
local records at [`product/pr_guardian/company_brain_records.py`](../product/pr_guardian/company_brain_records.py);
future operational products must do the same rather than importing PR-specific classes.
[`CompanyBrainFeedbackProjector`](../company_brain/feedback.py) then records those typed findings
and explicit outcomes as `finding` and `outcome` entities. It does **not** copy product evidence
references into the Brain because those references do not carry the original source ACL; the source
evidence must first enter through a governed projector.

## Explicit non-goals

- This core is not a global unrestricted knowledge lake or an unbounded agent memory.
- It does not replace source-of-truth systems or flatten their access controls.
- It does not infer causality, ownership, or approval from raw text alone.
- It does not grant L3/L4 action authority; that remains service, environment, and runbook
  specific under the production evidence contract.
