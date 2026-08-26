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
| [`../roadmap/technical-roadmap-24-months.md`](../roadmap/technical-roadmap-24-months.md) | Target proposal | Outcome-gated delivery sequence and promotion gates |
| [`CURRENT-POSITION.md`](CURRENT-POSITION.md) | Current implementation state | The single answer to "where are we today", with both yardsticks stated |
| [`PRODUCTION-EVIDENCE.md`](PRODUCTION-EVIDENCE.md) | Current evidence contract | What must be retained to support a promotion claim |
| [`PRODUCTION-PROOF-PLAN.md`](PRODUCTION-PROOF-PLAN.md) | Target promotion plan | Required sequence and gates |
| [`../architecture/MATURITY-SCORECARD.md`](../architecture/MATURITY-SCORECARD.md) | Current repository assessment | Directional maturity, never production proof |
| [`../architecture/ALIGNMENT-REVIEW.md`](../architecture/ALIGNMENT-REVIEW.md) | Historical review | Pre-corrective baseline only |
| [`architecture-review-2026-08.md`](architecture-review-2026-08.md) | Historical review | Point-in-time assessment only |
| [`../architecture/faang-multi-cloud-and-on-prem-extensions.md`](../architecture/faang-multi-cloud-and-on-prem-extensions.md) | Target proposal | Multi-cloud and air-gapped target architecture |
| [`../architecture/adr/001-temporal-control-plane.md`](../architecture/adr/001-temporal-control-plane.md) | Current design | Decision record mandating Temporal control plane |
| [`../architecture/adr/002-prompt-injection-and-caching.md`](../architecture/adr/002-prompt-injection-and-caching.md) | Target proposal | Proposed decision for guardrails and caching |
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
| [`KNOWLEDGE-INGEST-RUNBOOK.md`](KNOWLEDGE-INGEST-RUNBOOK.md) | Current implementation state | Ingestion runner and workflow; Azure path requirements |
| [`evidence/README.md`](evidence/README.md) | Current evidence contract | The evidence registry; an empty directory means not proven |
| [`OPERATIONS-INTELLIGENCE-RUNBOOK.md`](OPERATIONS-INTELLIGENCE-RUNBOOK.md) | Current implementation state | L1/L2 routes, secret, evidence modes, what an L2 proposal is not |
| [`L3-REHEARSAL-RUNBOOK.md`](L3-REHEARSAL-RUNBOOK.md) | Current implementation state | Exercise, soak, and readiness runners; rehearsal is not certification |
| [`COMPANY-BRAIN-CORE.md`](COMPANY-BRAIN-CORE.md) | Target proposal | Company Brain feedback loop (merged from a parallel line; not reconciled with ADR-001) |
| [`COMPANY-BRAIN-STORE.md`](COMPANY-BRAIN-STORE.md) | Target proposal | Company Brain reference store (merged from a parallel line) |

## Review cadence

- Update implementation state and scorecard in the same pull request as a material capability
  change.
- Update target design and NFRs before a change that affects trust boundaries, data handling,
  production policy, or autonomy.
- Reclassify a review as historical when later work invalidates its observed state.
- Review active documents at least quarterly; do not renew a status merely by changing its date.
