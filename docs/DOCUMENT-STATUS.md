# Documentation Governance and Register

| | |
|---|---|
| **Classification** | Current documentation-governance policy and document register |
| **Owner** | Platform Engineering |
| **Reviewed** | 2026-09-03 against origin/main at f556e16 |
| **Authoritative current state** | [Current Position](CURRENT-POSITION.md) |
| **Entry point** | [Company Brain Documentation](README.md) |

This register makes the repository navigable without creating a second source of product or
runtime truth. It records which document answers which question, how long its statements remain
authoritative, and where historical reviews have been reconciled.

## Authority and claim rules

### One question, one primary source

| Question | Canonical source | Do not substitute |
|---|---|---|
| What is true today? | [Current Position](CURRENT-POSITION.md) | A roadmap, review, score, test, or README summary |
| What source capabilities exist and what remains? | [Capability Reconciliation](../architecture/CAPABILITY-RECONCILIATION.md) | A target architecture diagram or historical finding |
| What is the product decision? | [Product Strategy](PRODUCT-STRATEGY.md) | A board narrative or a feature implementation detail |
| What constrains a design? | [System Design](../architecture/design.md), [NFRs](../architecture/non-functional-requirements.md), and [ADRs](../architecture/adr/README.md) | A backlog item or an unratified review recommendation |
| What work is sequenced next? | [Outcome-Gated Roadmap](../roadmap/technical-roadmap-24-months.md) | The A–Z workstream catalogue or historical remediation plan |
| What proves a pilot, deployment, or autonomy claim? | [Production Evidence Registry](PRODUCTION-EVIDENCE.md) | Green CI, a reference test, a workflow artifact, or a source contract |
| What did an earlier review observe? | [Review Archive](reviews/README.md) and [Findings Register](reviews/REVIEW-STATUS-REGISTER.md) | Its conclusions as a current status update |

### Approved claim vocabulary

Use these terms literally. They prevent a source-level reference implementation from being
mistaken for a deployed or certified product.

| Term | Meaning |
|---|---|
| **Current design** | Approved target architecture, invariants, or decision constraints. It is not a deployment claim. |
| **Current implementation state** | What source, configuration, or a named environment contains at a stated revision. |
| **Reference contract / runbook** | An executable, CI-covered source boundary or an operator procedure for that boundary. |
| **Target proposal** | A roadmap, model, or intended future state; it is planning material only. |
| **Evidence contract** | The required structure and retention rules for proving a claim. It is not evidence itself. |
| **Operationally proven** | Supported by a retained evidence record for the exact service, environment, data, and autonomy scope. |
| **Historical review** | Point-in-time observation retained for rationale. It cannot create an active backlog or current claim. |
| **Resolved / superseded / deferred** | A disposition in the [Review Findings Register](reviews/REVIEW-STATUS-REGISTER.md), not an assertion inside a historical finding. |

The absence of an evidence record means **not proven**. “Implemented,” a passing test, a green
CI run, a diagram, or a chart render does not mean deployed, pilot-ready, production-ready, or
autonomy-certified.

## Document lifecycle

1. Write a decision, design, contract, or runbook in the document set below.
2. Link to the one canonical source instead of restating its status or metrics.
3. Review the document when its stated trigger changes; add a revision or decision date.
4. Reclassify a dated assessment as historical when later work changes its observed state.
5. Record a historical finding’s disposition in the review register; preserve the original review
   text so the decision trail remains auditable.
6. Retire a document only by replacing it with a short redirect that names its successor. Do not
   break stable links or silently delete engineering rationale.

Every maintained standalone document must appear in this register. The register supplies its
lifecycle and primary purpose, and **Platform Engineering** is the default document owner unless
the document declares a more specific owner. A document must carry local control metadata when
it makes a current-state claim, records a decision, or assigns an operational responsibility;
otherwise it inherits the register's owner and review cadence. This keeps document control
visible without copying stale headers into every narrow reference contract. The repository README,
a generated artifact, and immutable ADRs may use their documented equivalent metadata instead.

The register's review date validates its navigation and lifecycle assignments only. It does not
refresh a capability, operational, or production claim: those claims require the revision,
decision date, or retained evidence named by their own authoritative document.

The registered documentation set is the repository README plus Markdown under `docs/`,
`architecture/`, `roadmap/`, `governance/`, `finops/`, and `helm/temporal/`. The repository link
check verifies that every document in that set appears in this register. Adding a document there
without registering it is therefore a CI failure, not a navigation debt for a later cleanup.

## Maintained document register

### Entry points and current product state

| Document | Lifecycle | Primary purpose |
|---|---|---|
| [Repository README](../README.md) | Entry point | Concise product overview, local reference setup, and repository map. |
| [Documentation portal](README.md) | Entry point | Role-based reading order and navigation. |
| [Current Position](CURRENT-POSITION.md) | Current implementation state | The single answer to “where are we today?” across source and external evidence. |
| [Product Strategy](PRODUCT-STRATEGY.md) | Current product decision | Company Brain north star, PR Guardian wedge, and product promotion gates. |
| [Capability Reconciliation](../architecture/CAPABILITY-RECONCILIATION.md) | Current implementation state | Capability-by-capability source assessment and remaining depth. |
| [Maturity Scorecard](../architecture/MATURITY-SCORECARD.md) | Current repository assessment | Directional source maturity; never production proof. |

### Architecture and decisions

| Document | Lifecycle | Primary purpose |
|---|---|---|
| [System Design](../architecture/design.md) | Current design | Five-plane architecture, invariants, data flow, and alternatives. |
| [Non-Functional Requirements](../architecture/non-functional-requirements.md) | Current design | Required operational, safety, security, and quality properties. |
| [Authoritative State](../architecture/authoritative-state.md) | Current design | Workflow state, audit, concurrency, and recovery boundary. |
| [Durable Orchestration](../architecture/durable-orchestration.md) | Current design | Separation of workflow state and execution scheduling. |
| [Organizational Memory](../architecture/organizational-memory.md) | Current design | Governed non-code knowledge ingestion model. |
| [Runtime Observability](../architecture/runtime-observability.md) | Current design | Correlation, telemetry, AI security, and FinOps expectations. |
| [Azure/AKS Self-Healing Reference](../architecture/azure-devops-self-healing-reference.md) | Target proposal | Target Azure, AKS, and self-healing composition. |
| [Multi-Cloud and On-Prem Extensions](../architecture/faang-multi-cloud-and-on-prem-extensions.md) | Target proposal | Deliberately deferred portability and air-gapped extensions. |
| [L4 Certification](../architecture/l4-certification.md) | Current design | Scope and certification constraints for bounded autonomy. |
| [ADR Index](../architecture/adr/README.md) | Current design | Decision record lifecycle and index. |
| [ADR-001: Temporal Control Plane](../architecture/adr/001-temporal-control-plane.md) | Accepted decision | Durable-control-plane technology decision. |
| [ADR-002: Prompt Injection and Caching](../architecture/adr/002-prompt-injection-and-caching.md) | Proposed decision | Guardrail and caching proposal; not an implemented-control claim. |
| [ADR-003: Company Brain Runtime Topology](../architecture/adr/003-company-brain-runtime-topology-and-recovery.md) | Accepted decision | Durable ownership, topology, and recovery boundary. |
| [Vertical Slice Milestone](../architecture/milestones/vertical-slice.md) | Historical implementation milestone | M2 reference-slice record. |
| [Production Ingestion Milestone](../architecture/milestones/m3-production-ingestion.md) | Historical implementation milestone | M3 ingestion reference-slice record. |
| [Secure Azure Foundation Milestone](../architecture/milestones/secure-azure-foundation.md) | Historical implementation milestone | Private Azure foundation reference-IaC record. |

### Company Brain and PR Guardian contracts

| Document | Lifecycle | Primary purpose |
|---|---|---|
| [Company Brain Core](COMPANY-BRAIN-CORE.md) | Reference contract | Product-neutral entities, relationships, evidence, provenance, and safe product use. |
| [Company Brain Store](COMPANY-BRAIN-STORE.md) | Reference contract | Tenant-scoped durable reference-store semantics. |
| [Company Brain World Model](COMPANY-BRAIN-WORLD-MODEL.md) | Reference contract | Qualified, read-only context and uncertainty rules. |
| [Company Brain Memory Sync](COMPANY-BRAIN-MEMORY-SYNC.md) | Reference contract | Governed source lifecycle projection into memory. |
| [Company Brain Maintenance](COMPANY-BRAIN-MAINTENANCE.md) | Reference contract | Read-only maintenance proposal and independent outcome correlation. |
| [PR Guardian Domain Contract](PR-GUARDIAN-DOMAIN-CONTRACT.md) | Reference contract | Product records and safety boundary. |
| [PR Guardian / Company Brain](PR-GUARDIAN-COMPANY-BRAIN.md) | Reference contract | Qualified context integration and durable feedback boundary. |
| [PR Guardian Repository Configuration](PR-GUARDIAN-REPOSITORY-CONFIG.md) | Reference contract | Repository-owned mode, rules, waivers, and kill switch. |
| [PR Guardian Pilot Readiness](PR-GUARDIAN-PILOT-READINESS.md) | Operator preflight | Read-only target-repository contract readiness report. |
| [PR Guardian Pilot Onboarding](PR-GUARDIAN-PILOT-ONBOARDING.md) | Reference contract | Shadow-only manifest and validation requirements. |
| [PR Guardian Shadow Pilot](PR-GUARDIAN-SHADOW-PILOT.md) | Operating runbook | Safe workflow split, reviewer feedback, operation, and stop conditions. |
| [PR Guardian Shadow Report](PR-GUARDIAN-SHADOW-REPORT.md) | Reference contract | Calculated feedback report and its explicit non-authority. |
| [PR Guardian Promotion Review](PR-GUARDIAN-PROMOTION-REVIEW.md) | Operating runbook | Evidence-bound, human review packet; never self-authorizing. |

### Engineering, operations, and evidence

| Document | Lifecycle | Primary purpose |
|---|---|---|
| [Application Configuration](APPLICATION-CONFIGURATION.md) | Reference contract | Typed HTTP-process settings and capability composition. |
| [Dependency Resilience](DEPENDENCY-RESILIENCE.md) | Reference contract | Synchronous dependency failure bounds and explicit limits. |
| [Ingestion Architecture](INGESTION.md) | Current implementation state | Ingestion pipeline and its operational boundaries. |
| [Knowledge Ingest Runbook](KNOWLEDGE-INGEST-RUNBOOK.md) | Operating runbook | How to execute and validate governed ingestion. |
| [Integration Proof Runbook](INTEGRATION-PROOF-RUNBOOK.md) | Operating runbook | Manual, private-runner-only integration validation. |
| [Operations Intelligence Runbook](OPERATIONS-INTELLIGENCE-RUNBOOK.md) | Operating runbook | L1 analysis and L2 human-only proposals. |
| [Temporal Worker Runbook](TEMPORAL-WORKER-RUNBOOK.md) | Operating runbook | Evidence-worker boundary and required deployment inputs. |
| [L3 Rehearsal Runbook](L3-REHEARSAL-RUNBOOK.md) | Operating runbook | Rehearsal, soak, and readiness exercises. |
| [L4 Promotion Runbook](L4-PROMOTION-RUNBOOK.md) | Operating runbook | Scoped certification record and revocation conditions. |
| [Runtime Capability Contract](RUNTIME-CAPABILITY-CONTRACT.md) | Reference contract | Source-level agreement among code, Helm, Terraform, and declared scope. |
| [Requirements Traceability](REQUIREMENTS-TRACEABILITY.md) | Reference contract | Rendered requirements-to-evidence view from the baseline. |
| [Performance Evidence Contract](PERFORMANCE-EVIDENCE-CONTRACT.md) | Evidence contract | Target budgets and measured-artifact schema. |
| [Type-Safety Baseline](TYPE-SAFETY-BASELINE.md) | Reference quality contract | Static-analysis and dynamic-typing ratchet scope. |
| [Targeted Mutation Contract](TARGETED-MUTATION-CONTRACT.md) | Reference quality contract | Mutation gate for named dependency-boundary invariants. |
| [Production Evidence Registry](PRODUCTION-EVIDENCE.md) | Evidence contract | Required immutable evidence and expiration rules. |
| [Production Proof Plan](PRODUCTION-PROOF-PLAN.md) | Target promotion plan | Required sequence before a production claim. |
| [Production Readiness](PRODUCTION-READINESS.md) | Certification requirements | Functional, security, reliability, safety, and economic gates. |
| [Evidence Registry](evidence/README.md) | Evidence contract | Registry usage; an empty registry means not proven. |
| [Temporal Helm README](../helm/temporal/README.md) | Deployment reference | Chart-specific local/deployment boundary. |

### Program, governance, and communication

| Document | Lifecycle | Primary purpose |
|---|---|---|
| [Outcome-Gated Product Maturity Roadmap](../roadmap/technical-roadmap-24-months.md) | Target proposal | The sole delivery sequencing and promotion-gate plan. |
| [A–Z Program Backlog](../roadmap/PROGRAM-BACKLOG.md) | Target proposal | Workstream catalogue; not a second execution sequence. |
| [Operating Model](../governance/operating-model.md) | Current design | Intended roles, decision rights, and governance cadence. |
| [Security Threat Model](../governance/security-threat-model.md) | Current design | Threats, controls, and explicit planned controls. |
| [KPI System](kpi-system.md) | Current design | Metric definitions and measurement basis. |
| [FinOps ROI Model](../finops/cfo-roi-model.md) | Target proposal | Modeled value and investment gates. |
| [Executive Memo](executive-memo.md) | Target proposal | Concise leadership narrative and modeled business rationale. |
| [Board Deck Narrative](board-deck-narrative.md) | Target proposal | Board-level narrative, not evidence of outcomes. |

### Historical archive

| Document | Lifecycle | Primary purpose |
|---|---|---|
| [Review Archive](reviews/README.md) | Archive index | How to read dated reviews without treating them as current work. |
| [Review Findings Register](reviews/REVIEW-STATUS-REGISTER.md) | Current reconciliation record | Disposition of historical findings and their living source of truth. |
| [Engineering Review](reviews/ENGINEERING_REVIEW.md) | Historical review | Baseline Company Brain architecture, codebase, and maturity review. |
| [Engineering Review Addendum](reviews/ENGINEERING_REVIEW_V2.md) | Historical review | Post-quality-wave correction to the baseline review. |
| [Skill-Driven Documentation Review](reviews/skill-driven-doc-review.md) | Historical review | Point-in-time documentation/process audit. |
| [Architecture & Implementation Review (2026-08)](architecture-review-2026-08.md) | Historical review | Pre-corrective implementation assessment. |
| [Architecture Alignment Review](../architecture/ALIGNMENT-REVIEW.md) | Historical review | Pre-corrective alignment assessment. |

## Change control and review cadence

- Update **Current Position** and, when applicable, **Capability Reconciliation** in the same
  pull request as a material source capability change.
- Update the target design, NFRs, threat model, and relevant ADR before changing a trust boundary,
  data lifecycle rule, production policy, autonomy tier, or authoritative-data ownership.
- Update the roadmap only for a changed outcome, dependency, sequence, or exit gate—not merely
  because an implementation branch merged.
- Add or amend operational evidence only through the evidence registry. Never promote a capability
  by editing prose.
- Review current documents at least quarterly and after a material incident, architecture decision,
  or product-scope change. Do not refresh a date without checking its recorded claims.
- Keep historical reviews immutable in substance. Add their resolution to the review register
  instead of silently rewriting their original observation.
