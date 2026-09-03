# Historical Review Findings Register

| | |
|---|---|
| **Classification** | Current reconciliation of historical-review findings |
| **Owner** | Platform Engineering |
| **Reviewed** | 2026-09-03 against origin/main at f556e16 |
| **Current state** | [Current Position](../CURRENT-POSITION.md) |
| **Evidence rule** | A resolved source finding is not a deployment, pilot, or production certification claim. |

This register prevents old findings and old delivery plans from becoming a second backlog. It
does not alter the historical record: **resolved** means the original source-level defect or
documentation inconsistency has an identified successor/control; it does not erase remaining
operational evidence requirements.

## Disposition vocabulary

| Disposition | Meaning |
|---|---|
| **Resolved in source** | The historical defect has an implemented, regression-covered repository control. |
| **Resolved as documentation governance** | The old ambiguity is replaced by a canonical source and change-control rule. |
| **Partially resolved** | A safe reference boundary exists, but a material production or operational constraint remains. |
| **Deferred by product decision** | Work remains intentionally outside the active product sequence. |
| **Superseded** | The original recommendation is no longer the correct plan; use the named living document. |

## Architecture & Implementation Review (2026-08)

The original review remains at [architecture-review-2026-08.md](../architecture-review-2026-08.md).
Its finding labels are historical severities, not current priorities.

| Historical finding | Current disposition | Living source of truth |
|---|---|---|
| P0-1 — CI could not collect tests | **Resolved in source.** Repository CI now exercises tests, policy, container, SBOM, and smoke checks. | [Current Position](../CURRENT-POSITION.md), [Type-Safety Baseline](../TYPE-SAFETY-BASELINE.md) |
| P0-2 — incompatible ingestion domain models | **Resolved in source.** Obsolete model names no longer form an active package boundary; current ingestion depth remains evidence-gated. | [Capability Reconciliation](../../architecture/CAPABILITY-RECONCILIATION.md), [Ingestion Architecture](../INGESTION.md) |
| P0-3 — header-asserted Azure identity | **Resolved in source for the Azure boundary.** The deterministic demo remains explicitly non-production. | [Threat Model](../../governance/security-threat-model.md), [NFRs](../../architecture/non-functional-requirements.md) |
| P1-4/P1-5 — retrieval schema and ACL parity | **Partially resolved.** The source contract supports ACL-bearing lexical/vector retrieval; real-index and denied-path evidence remain required. | [Capability Reconciliation](../../architecture/CAPABILITY-RECONCILIATION.md), [Production Evidence](../PRODUCTION-EVIDENCE.md) |
| P1-6 — OPA disconnected or divergent | **Resolved in source.** OPA and local policy conformance are gated; bundle distribution and operational proof remain open. | [Capability Reconciliation](../../architecture/CAPABILITY-RECONCILIATION.md), [L4 Promotion Runbook](../L4-PROMOTION-RUNBOOK.md) |
| P1-7 — fabricated retrieval evaluation | **Resolved in source.** Evaluation uses the repository’s real reference path and a versioned golden set. | [Capability Reconciliation](../../architecture/CAPABILITY-RECONCILIATION.md) |
| P2-8 — embeddings absent | **Resolved in source.** Vector-capable ingestion/retrieval is present; corpus-scale quality is not proven. | [Capability Reconciliation](../../architecture/CAPABILITY-RECONCILIATION.md), [Performance Evidence Contract](../PERFORMANCE-EVIDENCE-CONTRACT.md) |
| P2-9 — gateway metering/rate controls | **Partially resolved.** Budget and telemetry contracts exist; per-principal admission, quotas, and anomaly alerting remain planned. | [Threat Model](../../governance/security-threat-model.md), [NFRs](../../architecture/non-functional-requirements.md) |
| P2-10 — retrieved-content injection defenses | **Partially resolved.** Evidence is treated as untrusted and adversarial controls exist; the dedicated guardrail control remains planned. | [Threat Model](../../governance/security-threat-model.md) |
| P2-11 — unused src and provider stubs | **Resolved in source.** The obsolete prototypes were retired. | [Current Position](../CURRENT-POSITION.md) |
| P2-12 — image and workload hardening drift | **Resolved in source for reference packaging.** Deployment and operational evidence remain required. | [Runtime Capability Contract](../RUNTIME-CAPABILITY-CONTRACT.md), [Production Proof Plan](../PRODUCTION-PROOF-PLAN.md) |
| P3-13 — README/documentation drift | **Resolved as documentation governance.** The portal, register, authority model, and link/anchor CI checks now own this concern. | [Documentation Governance and Register](../DOCUMENT-STATUS.md) |
| P3-14 — smaller correctness and hygiene items | **Superseded.** The specific findings are distributed to current contracts and capability rows rather than carried as one historical bucket. | [Capability Reconciliation](../../architecture/CAPABILITY-RECONCILIATION.md), [Requirements Traceability](../REQUIREMENTS-TRACEABILITY.md) |

## Engineering Review and quality-wave addendum

The [Engineering Review](ENGINEERING_REVIEW.md) and [Engineering Review Addendum](ENGINEERING_REVIEW_V2.md)
record the five-pillar baseline and quality-wave correction. Their historical delivery plan is
superseded by the outcome-gated roadmap.

| Historical theme | Current disposition | Living source of truth |
|---|---|---|
| Runtime kill switches, configuration truth, package truth, correlation | **Resolved in source.** These are reference controls, not deployed controls. | [Runtime Capability Contract](../RUNTIME-CAPABILITY-CONTRACT.md), [Application Configuration](../APPLICATION-CONFIGURATION.md) |
| Static-analysis/type-system debt | **Resolved in source for the distributable-package ratchet.** It is a floor, not a claim that every dynamic boundary is flawless. | [Type-Safety Baseline](../TYPE-SAFETY-BASELINE.md) |
| Requirements, policy conformance, performance evidence | **Resolved as reference contracts.** Measured performance and production evidence remain open. | [Requirements Traceability](../REQUIREMENTS-TRACEABILITY.md), [Performance Evidence Contract](../PERFORMANCE-EVIDENCE-CONTRACT.md) |
| Shared Company Brain contracts | **Resolved in source.** PR Guardian is the demonstrated first consumer; reuse by a second product remains future evidence. | [Company Brain Core](../COMPANY-BRAIN-CORE.md) |
| PR Guardian pilot and promotion | **Partially resolved.** Safe onboarding, readiness, shadow reporting, and promotion-packet mechanics exist; a named pilot and retained human outcomes do not. | [Product Strategy](../PRODUCT-STRATEGY.md), [Pilot Readiness](../PR-GUARDIAN-PILOT-READINESS.md), [Production Evidence](../PRODUCTION-EVIDENCE.md) |
| Company Brain maintenance loop | **Resolved in source as read-only planning and outcome correlation.** No source publisher or real outcome effectiveness is claimed. | [Company Brain Maintenance](../COMPANY-BRAIN-MAINTENANCE.md) |

## Skill-driven documentation review

The [Skill-Driven Documentation Review](skill-driven-doc-review.md) is preserved as an external
framework exercise. Its references to external board material remain non-repository context.

| Historical handoff category | Current disposition | Living source of truth |
|---|---|---|
| Documentation hierarchy and authority | **Resolved as documentation governance.** | [Documentation Governance and Register](../DOCUMENT-STATUS.md) |
| Product pilot, operating model, governance | **Partially resolved.** Source contracts exist; real owners, pilot scope, and operational proof are external gates. | [Product Strategy](../PRODUCT-STRATEGY.md), [Operating Model](../../governance/operating-model.md), [Production Evidence](../PRODUCTION-EVIDENCE.md) |
| Latency/cost evidence | **Partially resolved.** Contract and target budgets exist; measured evidence remains open. | [Performance Evidence Contract](../PERFORMANCE-EVIDENCE-CONTRACT.md), [KPI System](../kpi-system.md) |

## Maintenance rule

When a material review finding is resolved or re-opened, update this register and its living
source in the same pull request. Do not change the original report’s historical conclusion to
make it look current.
