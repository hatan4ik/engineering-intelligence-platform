# Company Brain Core v1

| | |
|---|---|
| **Status** | Reference implementation — canonical model and projections, not a deployed system of record |
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

The initial store is in-memory and tested. A durable adapter is a later implementation stage and
must preserve the core’s ID, provenance, ACL, idempotency, and relationship-validation rules.

`IngestionPipeline` now accepts an optional `CompanyBrainProjector`. This keeps existing ingestion
callers backward compatible while allowing a governed file change to update the retrieval index,
source catalog, and Company Brain projection only after the index write succeeds.

## Safe product use

[`PRGuardianCompanyBrainAdapter`](../product/pr_guardian/company_brain.py) converts the core into
the existing PR Guardian service graph and evidence contract. It is read-only:

- authorized evidence becomes a cited `EvidenceBundle`;
- inaccessible evidence is omitted and produces a limitation;
- the service/dependency graph calculates deterministic blast radius; and
- no adapter result can approve, block, merge, deploy, or change OPA policy.

This is the integration pattern for subsequent Company Brain products: consume a constrained,
authorized context; emit a reviewable outcome; then return explicit feedback and independently
correlated outcomes to governed organizational memory.

[`CompanyBrainFeedbackProjector`](../company_brain/feedback.py) now records typed PR findings and
explicit reviewer outcomes as `finding` and `outcome` entities. It does **not** copy product
evidence references into the Brain because those references do not carry the original source ACL;
the source evidence must first enter through a governed projector.

## Explicit non-goals

- This core is not a global unrestricted knowledge lake or an unbounded agent memory.
- It does not replace source-of-truth systems or flatten their access controls.
- It does not infer causality, ownership, or approval from raw text alone.
- It does not grant L3/L4 action authority; that remains service, environment, and runbook
  specific under the production evidence contract.
