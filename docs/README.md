# Company Brain Documentation

| | |
|---|---|
| **Classification** | Documentation entry point and navigation only |
| **Owner** | Platform Engineering |
| **Reviewed** | 2026-09-04 against `main` at `615c402` |
| **Product** | Company Brain — governed organizational memory, qualified reasoning, and controlled action |
| **Repository** | Engineering Intelligence Platform reference implementation |
| **Authoritative status** | [Current Position](CURRENT-POSITION.md) |
| **Documentation governance** | [Documentation Governance and Register](DOCUMENT-STATUS.md) |

This is the reading map for the repository. It does not make a capability, deployment, or
production claim. For a claim about what exists today, use **Current Position** first; for
evidence that supports a promotion, use the **Production Evidence Registry**.

## Start here

1. Read the [repository overview](../README.md) for the product thesis and local reference
   workflow.
2. Read [Current Position](CURRENT-POSITION.md) for verified source state, open external gates,
   and the roadmap stage.
3. Read [Product Strategy](PRODUCT-STRATEGY.md) for the deliberate first product decision:
   PR Guardian is the narrow, non-blocking Company Brain wedge.
4. Read the [System Design](../architecture/design.md) for the target architecture and invariants.

Need a term expanded? Use the [Company Brain Glossary](GLOSSARY.md). Marked abbreviations provide
a desktop hover hint and the glossary remains the accessible, canonical definition.

## Reading paths by role

| If you are… | Read in this order | Use it to answer |
|---|---|---|
| Product or engineering leader | [Current Position](CURRENT-POSITION.md) → [Product Strategy](PRODUCT-STRATEGY.md) → [Roadmap](../roadmap/technical-roadmap-24-months.md) → [KPI System](kpi-system.md) | What is the product, what is actually ready, and what outcome earns the next investment? |
| Architect | [System Design](../architecture/design.md) → [<span title="Non-Functional Requirements">NFRs</span>](../architecture/non-functional-requirements.md) → [<span title="Architecture Decision Records">ADRs</span>](../architecture/adr/README.md) → [Capability Reconciliation](../architecture/CAPABILITY-RECONCILIATION.md) | What constraints govern a design change, and which portions are reference versus target state? |
| Product engineer | [Product Strategy](PRODUCT-STRATEGY.md) → [Company Brain Core](COMPANY-BRAIN-CORE.md) → [PR Guardian Domain Contract](PR-GUARDIAN-DOMAIN-CONTRACT.md) → relevant component contract or runbook | Which problem, records, boundaries, and safety rules apply to this change? |
| Pilot operator | [Pilot Readiness](PR-GUARDIAN-PILOT-READINESS.md) → [Pilot Onboarding](PR-GUARDIAN-PILOT-ONBOARDING.md) → [Shadow Pilot](PR-GUARDIAN-SHADOW-PILOT.md) → [Promotion Review](PR-GUARDIAN-PROMOTION-REVIEW.md) | How do we prepare a shadow-only pilot without mistaking source validation for authorization? |
| <span title="Site Reliability Engineering">SRE</span> or security reviewer | [Production Evidence](PRODUCTION-EVIDENCE.md) → [Production Readiness](PRODUCTION-READINESS.md) → [Threat Model](../governance/security-threat-model.md) → relevant <span title="Autonomy Level 3 — approve and execute">L3</span>/<span title="Autonomy Level 4 — bounded autonomous">L4</span> runbook | What proof is required before real data, automation, or autonomy is allowed? |
| Contributor maintaining a reference path | [Application Configuration](APPLICATION-CONFIGURATION.md) → [Runtime Capability Contract](RUNTIME-CAPABILITY-CONTRACT.md) → [Requirements Traceability](REQUIREMENTS-TRACEABILITY.md) → [Document Register](DOCUMENT-STATUS.md) | What source-level contract and documentation updates belong in the same pull request? |

## Authority model

One question has one primary answer. Supporting documents may explain or provide evidence, but
must link back rather than restate competing status.

| Question | Primary document | Supporting material |
|---|---|---|
| What is true in this repository now? | [Current Position](CURRENT-POSITION.md) | [Capability Reconciliation](../architecture/CAPABILITY-RECONCILIATION.md), [Maturity Scorecard](../architecture/MATURITY-SCORECARD.md) |
| What are we building and why? | [Product Strategy](PRODUCT-STRATEGY.md) | [Executive Memo](executive-memo.md), [System Design](../architecture/design.md) |
| What architecture and invariants constrain change? | [System Design](../architecture/design.md) | [NFRs](../architecture/non-functional-requirements.md), [ADRs](../architecture/adr/README.md), [Threat Model](../governance/security-threat-model.md) |
| What work comes next? | [Outcome-Gated Roadmap](../roadmap/technical-roadmap-24-months.md) | [Program Backlog](../roadmap/PROGRAM-BACKLOG.md) |
| What proves a real-world claim? | [Production Evidence Registry](PRODUCTION-EVIDENCE.md) | [Production Proof Plan](PRODUCTION-PROOF-PLAN.md), [Performance Evidence Contract](PERFORMANCE-EVIDENCE-CONTRACT.md) |
| How does an operator run a reference workflow? | The relevant runbook below | [Runtime Capability Contract](RUNTIME-CAPABILITY-CONTRACT.md) |
| What did a prior review conclude? | [Review Archive](reviews/README.md) | [Review Findings Register](reviews/REVIEW-STATUS-REGISTER.md) |

## Product and Company Brain contracts

| Document set | Purpose |
|---|---|
| [Company Brain Core](COMPANY-BRAIN-CORE.md) · [Durable Store](COMPANY-BRAIN-STORE.md) · [Qualified World Model](COMPANY-BRAIN-WORLD-MODEL.md) | Product-neutral memory, evidence, relationship, provenance, and qualified-read boundaries. |
| [Memory Synchronization](COMPANY-BRAIN-MEMORY-SYNC.md) · [Memory Maintenance](COMPANY-BRAIN-MAINTENANCE.md) | Governed lifecycle projection and read-only dreaming/pruning proposals. |
| [PR Guardian Domain Contract](PR-GUARDIAN-DOMAIN-CONTRACT.md) · [PR Guardian / Company Brain](PR-GUARDIAN-COMPANY-BRAIN.md) | PR Guardian records, limits, and safe use of qualified Company Brain context. |
| [Repository Configuration](PR-GUARDIAN-REPOSITORY-CONFIG.md) | Repository-owned mode, waiver, kill-switch, and deterministic rule contract. |
| [Pilot Readiness](PR-GUARDIAN-PILOT-READINESS.md) · [Pilot Onboarding](PR-GUARDIAN-PILOT-ONBOARDING.md) · [Shadow Pilot](PR-GUARDIAN-SHADOW-PILOT.md) | The only supported preparation and operation sequence for a target repository. |
| [Shadow Report](PR-GUARDIAN-SHADOW-REPORT.md) · [Promotion Review](PR-GUARDIAN-PROMOTION-REVIEW.md) | Feedback calculation and the non-authorizing, evidence-bound human review packet. |

## Architecture and engineering contracts

| Area | Documents |
|---|---|
| Target architecture | [System Design](../architecture/design.md) · [Authoritative State](../architecture/authoritative-state.md) · [Durable Orchestration](../architecture/durable-orchestration.md) · [Organizational Memory](../architecture/organizational-memory.md) · [Runtime Observability](../architecture/runtime-observability.md) |
| Architecture decisions | [<span title="Architecture Decision Record">ADR</span> index](../architecture/adr/README.md) · [Temporal control plane](../architecture/adr/001-temporal-control-plane.md) · [Prompt injection and caching](../architecture/adr/002-prompt-injection-and-caching.md) · [Company Brain runtime topology](../architecture/adr/003-company-brain-runtime-topology-and-recovery.md) |
| Platform extensions | [Azure/AKS self-healing reference](../architecture/azure-devops-self-healing-reference.md) · [Multi-cloud and on-prem extensions](../architecture/faang-multi-cloud-and-on-prem-extensions.md) · [L4 certification](../architecture/l4-certification.md) |
| Source and runtime contracts | [Ingestion Architecture](INGESTION.md) · [HTTP Application Configuration](APPLICATION-CONFIGURATION.md) · [Dependency Resilience](DEPENDENCY-RESILIENCE.md) · [Runtime Capability Contract](RUNTIME-CAPABILITY-CONTRACT.md) |
| Quality and traceability | [Requirements Traceability](REQUIREMENTS-TRACEABILITY.md) · [Performance Evidence Contract](PERFORMANCE-EVIDENCE-CONTRACT.md) · [Type-Safety Baseline](TYPE-SAFETY-BASELINE.md) · [Targeted Mutation Contract](TARGETED-MUTATION-CONTRACT.md) |

## Operations, evidence, and governance

| Area | Documents |
|---|---|
| Reference operation | [Knowledge Ingest](KNOWLEDGE-INGEST-RUNBOOK.md) · [Integration Proof](INTEGRATION-PROOF-RUNBOOK.md) · [Operations Intelligence](OPERATIONS-INTELLIGENCE-RUNBOOK.md) · [Temporal Worker](TEMPORAL-WORKER-RUNBOOK.md) |
| Autonomy progression | [<span title="Autonomy Level 3 — approve and execute">L3</span> Rehearsal](L3-REHEARSAL-RUNBOOK.md) · [<span title="Autonomy Level 4 — bounded autonomous">L4</span> Promotion](L4-PROMOTION-RUNBOOK.md) · [Production Readiness](PRODUCTION-READINESS.md) |
| Evidence and proof | [Evidence Registry](evidence/README.md) · [Production Evidence](PRODUCTION-EVIDENCE.md) · [Production Proof Plan](PRODUCTION-PROOF-PLAN.md) |
| Governance and economics | [Operating Model](../governance/operating-model.md) · [Security Threat Model](../governance/security-threat-model.md) · [KPI System](kpi-system.md) · [FinOps ROI Model](../finops/cfo-roi-model.md) |

## Planning and historical material

- [Outcome-Gated Product Maturity Roadmap](../roadmap/technical-roadmap-24-months.md) is the
  delivery sequence. The [A–Z Program Backlog](../roadmap/PROGRAM-BACKLOG.md) is a workstream
  catalogue, not a second roadmap.
- [Executive Memo](executive-memo.md) and [Board Deck Narrative](board-deck-narrative.md) are
  target-state communication material. Their modeled outcomes are not current-state evidence.
- [Review Archive](reviews/README.md) and the [Historical Architecture Alignment Review](../architecture/ALIGNMENT-REVIEW.md)
  preserve context. They are never the source for current status or active work ordering.

## Maintaining this documentation

Follow the [Documentation Governance and Register](DOCUMENT-STATUS.md) when adding or changing a
document. Preserve stable links, update the authoritative current-state document in the same pull
request as a material capability change, and record resolved historical findings in the review
register rather than rewriting history.
