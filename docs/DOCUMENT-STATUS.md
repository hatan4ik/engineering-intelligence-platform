# Documentation Status and Freshness

| | |
|---|---|
| **Status** | Current documentation-governance policy |
| **Owner** | Platform Engineering |
| **Rule** | No document may imply a stronger implementation or production state than its evidence supports |

## Classification

| Label | Meaning | Use for decisions? |
|---|---|---|
| **Current design** | Approved target architecture and invariants | Yes, for intended design decisions |
| **Current implementation state** | What is present in the repository or a named environment at the stated revision | Yes, subject to linked evidence |
| **Target proposal** | Planned architecture or roadmap, not an implementation claim | Yes, for planning only |
| **Historical review** | Point-in-time analysis retained for context | No; use its stated date/revision only |
| **Generated evidence** | Reproducible report/artifact with scope and expiry | Yes, only for the claim and scope recorded |

## Required header fields

Any current architecture, readiness, scorecard, or capability document must state:

1. classification and owner;
2. reviewed date and, for implementation claims, commit or environment;
3. the authoritative current-state and production-evidence documents; and
4. whether its assertions are implemented, deployed, or production-proven.

Use links to tests, IaC, dashboards, signed artifacts, or evidence IDs for claims that affect
security, autonomy, reliability, quality, or economics. “Implemented” alone never means
production-certified.

## Canonical documents

| Document | Classification | Authority |
|---|---|---|
| [`../architecture/design.md`](../architecture/design.md) | Current design | System invariants and target architecture |
| [`../architecture/CAPABILITY-RECONCILIATION.md`](../architecture/CAPABILITY-RECONCILIATION.md) | Current implementation state | Reference implementation capability status and queue |
| [`../architecture/non-functional-requirements.md`](../architecture/non-functional-requirements.md) | Current design | Operational, data, and safety requirements |
| [`PRODUCT-STRATEGY.md`](PRODUCT-STRATEGY.md) | Current product decision | First product wedge and expansion gates |
| [`PR-GUARDIAN-DOMAIN-CONTRACT.md`](PR-GUARDIAN-DOMAIN-CONTRACT.md) | Current product boundary | PR Guardian records and safety invariants |
| [`PR-GUARDIAN-COMPANY-BRAIN.md`](PR-GUARDIAN-COMPANY-BRAIN.md) | Implemented reference contract | Qualified context, durable findings, and non-enforcement rules |
| [`PR-GUARDIAN-PILOT-ONBOARDING.md`](PR-GUARDIAN-PILOT-ONBOARDING.md) | Current implementation contract | Shadow-only target-repository onboarding record and local validator; not pilot activation |
| [`PR-GUARDIAN-PROMOTION-REVIEW.md`](PR-GUARDIAN-PROMOTION-REVIEW.md) | Current implementation contract | Digest-bound human review packet; never a product authorization |
| [`../roadmap/technical-roadmap-24-months.md`](../roadmap/technical-roadmap-24-months.md) | Target proposal | Outcome-gated delivery sequence and promotion gates |
| [`CURRENT-POSITION.md`](CURRENT-POSITION.md) | Current implementation state | The single answer to "where are we today", with both yardsticks stated |
| [`PRODUCTION-EVIDENCE.md`](PRODUCTION-EVIDENCE.md) | Current evidence contract | What must be retained to support a promotion claim |
| [`PERFORMANCE-EVIDENCE-CONTRACT.md`](PERFORMANCE-EVIDENCE-CONTRACT.md) | Current design | Canonical target budgets and performance-observation artifact contract; not measured evidence |
| [`PRODUCTION-PROOF-PLAN.md`](PRODUCTION-PROOF-PLAN.md) | Target promotion plan | Required sequence and gates |
| [`APPLICATION-CONFIGURATION.md`](APPLICATION-CONFIGURATION.md) | Current implementation contract | Typed HTTP-process settings, startup validation, and capability composition |
| [`RUNTIME-CAPABILITY-CONTRACT.md`](RUNTIME-CAPABILITY-CONTRACT.md) | Current implementation contract | Source-only agreement between code, chart, Terraform, and declared runtime scope |
| [`DEPENDENCY-RESILIENCE.md`](DEPENDENCY-RESILIENCE.md) | Current implementation contract | Per-process synchronous dependency bounds and their explicit non-claims |
| [`../architecture/MATURITY-SCORECARD.md`](../architecture/MATURITY-SCORECARD.md) | Current repository assessment | Directional maturity, never production proof |
| [`reviews/ENGINEERING_REVIEW.md`](reviews/ENGINEERING_REVIEW.md) | Historical review with dated reconciliation | Baseline findings; use its stated revision and reconciliation scope only |
| [`reviews/ENGINEERING_REVIEW_V2.md`](reviews/ENGINEERING_REVIEW_V2.md) | Current implementation review addendum | Evidence-backed correction to the post-quality-wave draft; not a second scorecard |
| [`../architecture/ALIGNMENT-REVIEW.md`](../architecture/ALIGNMENT-REVIEW.md) | Historical review | Pre-corrective baseline only |
| [`architecture-review-2026-08.md`](architecture-review-2026-08.md) | Historical review | Point-in-time assessment only |
| [`../architecture/faang-multi-cloud-and-on-prem-extensions.md`](../architecture/faang-multi-cloud-and-on-prem-extensions.md) | Target proposal | Multi-cloud and air-gapped target architecture |
| [`../architecture/adr/001-temporal-control-plane.md`](../architecture/adr/001-temporal-control-plane.md) | Current design | Decision record mandating Temporal control plane |
| [`../architecture/adr/002-prompt-injection-and-caching.md`](../architecture/adr/002-prompt-injection-and-caching.md) | Target proposal | Proposed decision for guardrails and caching |
| [`../architecture/adr/003-company-brain-runtime-topology-and-recovery.md`](../architecture/adr/003-company-brain-runtime-topology-and-recovery.md) | Current design | Target Company Brain data ownership, durable topology, and recovery boundaries |
| [`../roadmap/PROGRAM-BACKLOG.md`](../roadmap/PROGRAM-BACKLOG.md) | Target proposal | Workstream themes; sequencing deferred to the roadmap stages |
| [`kpi-system.md`](kpi-system.md) | Current design | Metric definitions and measurement basis |
| [`../governance/operating-model.md`](../governance/operating-model.md) | Current design | Governance roles and cadence |
| [`../governance/security-threat-model.md`](../governance/security-threat-model.md) | Current design | Threats, controls, and the L0–L5 ladder |
| [`../architecture/l4-certification.md`](../architecture/l4-certification.md) | Current design | Scoped L4 certification rules |
| [`../architecture/durable-orchestration.md`](../architecture/durable-orchestration.md) | Current design | Workflow state vs. execution scheduling |
| [`../architecture/organizational-memory.md`](../architecture/organizational-memory.md) | Current design | Non-code knowledge sources |
| [`../architecture/runtime-observability.md`](../architecture/runtime-observability.md) | Current design | Correlation, AI security, FinOps telemetry |
| [`../architecture/milestones/vertical-slice.md`](../architecture/milestones/vertical-slice.md) | Current implementation state | Milestone 2 reference slice |
| [`../architecture/milestones/m3-production-ingestion.md`](../architecture/milestones/m3-production-ingestion.md) | Current implementation state | Milestone 3 ingestion reference |
| [`../architecture/milestones/secure-azure-foundation.md`](../architecture/milestones/secure-azure-foundation.md) | Current implementation state | Private Azure foundation reference IaC |
| [`executive-memo.md`](executive-memo.md) | Target proposal | Narrative; modeled benefits |
| [`board-deck-narrative.md`](board-deck-narrative.md) | Target proposal | Narrative; modeled benefits |
| [`reviews/skill-driven-doc-review.md`](reviews/skill-driven-doc-review.md) | Historical review | Point-in-time documentation audit |
| [`PR-GUARDIAN-SHADOW-REPORT.md`](PR-GUARDIAN-SHADOW-REPORT.md) | Current implementation state | What the shadow report computes and does not authorize |
| [`PR-GUARDIAN-REPOSITORY-CONFIG.md`](PR-GUARDIAN-REPOSITORY-CONFIG.md) | Current implementation state | Repository-owned modes, waivers, kill switch, threat model |
| [`TYPE-SAFETY-BASELINE.md`](TYPE-SAFETY-BASELINE.md) | Current implementation-quality contract | Versioned Ruff/mypy/dynamic-typing ratchet for core product and control packages |
| [`TARGETED-MUTATION-CONTRACT.md`](TARGETED-MUTATION-CONTRACT.md) | Current implementation-quality contract | Source-level mutation gate for named dependency-boundary safety invariants; not production evidence |
| [`KNOWLEDGE-INGEST-RUNBOOK.md`](KNOWLEDGE-INGEST-RUNBOOK.md) | Current implementation state | Ingestion runner and workflow; Azure path requirements |
| [`evidence/README.md`](evidence/README.md) | Current evidence contract | The evidence registry; an empty directory means not proven |
| [`OPERATIONS-INTELLIGENCE-RUNBOOK.md`](OPERATIONS-INTELLIGENCE-RUNBOOK.md) | Current implementation state | L1/L2 routes, secret, evidence modes, what an L2 proposal is not |
| [`L3-REHEARSAL-RUNBOOK.md`](L3-REHEARSAL-RUNBOOK.md) | Current implementation state | Exercise, soak, and readiness runners; rehearsal is not certification |
| [`L4-PROMOTION-RUNBOOK.md`](L4-PROMOTION-RUNBOOK.md) | Current implementation state | Scoped certification record, what invalidates it, the platform cannot self-certify |
| [`COMPANY-BRAIN-CORE.md`](COMPANY-BRAIN-CORE.md) | Current implementation contract | Product-neutral Evidence, Finding, Outcome, and provenance records; source-only reference behavior |
| [`COMPANY-BRAIN-STORE.md`](COMPANY-BRAIN-STORE.md) | Current implementation contract | Tenant-scoped Company Brain reference store; not a production data plane |
| [`COMPANY-BRAIN-WORLD-MODEL.md`](COMPANY-BRAIN-WORLD-MODEL.md) | Current implementation contract | Qualified Company Brain world-model read path; not action authority |
| [`COMPANY-BRAIN-MEMORY-SYNC.md`](COMPANY-BRAIN-MEMORY-SYNC.md) | Current implementation contract | Governed source lifecycle projection into reference memory |
| [`COMPANY-BRAIN-MAINTENANCE.md`](COMPANY-BRAIN-MAINTENANCE.md) | Current implementation contract | Read-only maintenance planning plus explicit review/source-observation correlation; no source publisher |

## Review cadence

- Update implementation state and scorecard in the same pull request as a material capability
  change.
- Update target design and NFRs before a change that affects trust boundaries, data handling,
  production policy, or autonomy.
- Reclassify a review as historical when later work invalidates its observed state.
- Review active documents at least quarterly; do not renew a status merely by changing its date.
