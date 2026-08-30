# Engineering Intelligence Platform: Developer Portal & Documentation

Welcome to the documentation for the Engineering Intelligence Platform. To prevent "doc rot" and ensure a clean reading experience, this repository uses the Diátaxis framework logic, separating high-level strategic vision from deep architectural operations.

## 🧭 Part 1: Strategic Vision & Executive Context
*Start here if you want to understand the "Why" and the business case.*
- [The Executive Memo](executive-memo.md) - The core problem, scaling tax, and high-level platform vision.
- [Board Deck Narrative](board-deck-narrative.md) - The 12-slide pitch for VP-level stakeholders.
- [Product Strategy (Initial Wedge)](PRODUCT-STRATEGY.md) - Why we start with PR Guardian before attempting self-healing.
- [Current Position](CURRENT-POSITION.md) - Where the platform stands today, on both yardsticks, with the per-stage engineering-vs-evidence table.

## 🛠 Runbooks (Stages 1–6 engineering)
*What each runner does, what it needs, and what it refuses to do.*
- [PR Guardian Shadow Report](PR-GUARDIAN-SHADOW-REPORT.md) · [PR Guardian Repository Config](PR-GUARDIAN-REPOSITORY-CONFIG.md)
- [Knowledge Ingest](KNOWLEDGE-INGEST-RUNBOOK.md) · [Evidence Registry](evidence/README.md) · [Integration Proof](INTEGRATION-PROOF-RUNBOOK.md)
- [Operations Intelligence (L1/L2)](OPERATIONS-INTELLIGENCE-RUNBOOK.md)
- [L3 Rehearsal](L3-REHEARSAL-RUNBOOK.md) · [L4 Promotion](L4-PROMOTION-RUNBOOK.md) · [Temporal Worker](TEMPORAL-WORKER-RUNBOOK.md)
- [24-Month Technical Roadmap](../roadmap/technical-roadmap-24-months.md)
- [CFO ROI Model](../finops/cfo-roi-model.md) - Value equation and investment gates.

## 🏗️ Part 2: Core Architecture
*Start here if you are a Staff/Principal Engineer evaluating the system design.*
- **[The Master System Design](../architecture/design.md)** - The most important technical document. Covers the 5 planes, LLMOps, Temporal, and Semantic Caching.
- [Security Threat Model](../governance/security-threat-model.md) - Trust boundaries and the L0–L5 autonomy tiers.
- [Multi-Cloud & On-Prem Kubernetes Self-Healing Reference](../architecture/azure-devops-self-healing-reference.md)
- [FAANG Multi-Cloud & On-Prem Extensions](../architecture/faang-multi-cloud-and-on-prem-extensions.md) - Air-gapped AI operations and deep K8s troubleshooting.

## 🔍 Part 3: Component Deep Dives
*Detailed engineering specs for individual planes.*
- **Knowledge Plane:** 
  - [Ingestion Architecture](INGESTION.md) - Chunking, ACLs, and out-of-band reconciliation loops.
  - [Organizational Memory](../architecture/organizational-memory.md) - Work items and incident ingestion.
- **Control Plane:**
  - [Durable Orchestration](../architecture/durable-orchestration.md) - Temporal workflows, crash recovery, and job queues.
  - [Authoritative State](../architecture/authoritative-state.md) - Hash-chained audit logs.

## ⚙️ Part 4: Operations, FinOps & Governance
*How we run the platform safely in production.*
- [KPI System](kpi-system.md) - AI-quality, safety, and FinOps metrics.
- [Runtime Observability](../architecture/runtime-observability.md) - OpenTelemetry and cost tracking.
- [HTTP Application Configuration](APPLICATION-CONFIGURATION.md) - Typed process settings, startup validation, and capability wiring.
- [L4 Certification Guidelines](../architecture/l4-certification.md) - How a service "earns" the right to self-heal.
- [Production Readiness Gates](PRODUCTION-READINESS.md)
- [Production Evidence Contract](PRODUCTION-EVIDENCE.md)
- [Performance and Evidence Contract](PERFORMANCE-EVIDENCE-CONTRACT.md)
- [Static Analysis and Type-Safety Baseline](TYPE-SAFETY-BASELINE.md)

## 🏛️ Part 5: Historical Reviews & ADRs
*Decisions made and past audits.*
- [Architecture Decision Records (ADRs)](../architecture/adr/)
- [Alignment Review](../architecture/ALIGNMENT-REVIEW.md)
- [Pre-Corrective Baseline Review (2026-08)](architecture-review-2026-08.md)
