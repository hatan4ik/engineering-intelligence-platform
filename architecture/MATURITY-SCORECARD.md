# Engineering Intelligence Platform — Original Architecture Maturity Scorecard

| | |
|---|---|
| **Classification** | Current repository assessment — directional, not production evidence |
| **Owner** | Platform Engineering |
| **Production evidence** | [`../docs/PRODUCTION-EVIDENCE.md`](../docs/PRODUCTION-EVIDENCE.md) |

This scorecard prevents implementation drift. It measures the repository against the **original
Engineering Intelligence Platform architecture**, not against the amount of code in any one
subsystem. Scores are deliberately capped at reference maturity until environment-scoped,
retained operational evidence exists; a checked-in adapter, test, or diagram is not a level-4
claim.

## Maturity scale

- **0 — absent:** no meaningful implementation.
- **1 — concept:** documentation/contracts only.
- **2 — prototype:** executable local slice, narrow fixtures/integration.
- **3 — reference implementation:** coherent E2E path with tests, still limited operational breadth.
- **4 — production-capable:** real provider boundaries, security/reliability controls, measurable outcomes; remaining work is scale/calibration/operations.
- **5 — production-proven:** deployed operationally with retained evidence, SLO history, measured quality/value and repeated failure exercises.

## Current scorecard

| Original capability | Maturity | Evidence now present | To reach next level |
|---|---:|---|---|
| Architecture coherence / governance | **3.5** | north-star, ADR invariants, capability reconciliation, L0–L4 boundary | operate the model with named owners and outcome evidence |
| Secure Azure foundation | **2.5** | private AI/Search/Key Vault, Private Link/DNS, AKS Workload Identity reference IaC | production ingress/egress, hardened workload, state/queue, scale and DR exercises |
| Code ingestion | **3.5** | GitHub/ADO events, AST chunks, ACL metadata, ledger/DLQ/replay, source lifecycle/ACL reconciliation/deletion/index repair | managed provider scheduling, shared durable queue/backpressure, broader source adapters, and live source evidence |
| Organizational engineering memory | **2.5** | governed model and normalizers | live enterprise credentials/sync, broader ACL resolution, source SLAs, and lifecycle controls |
| Hybrid/vector RAG | **2.5** | vector/hybrid retrieval and ACL-trimming reference path | real retriever evaluation, corpus-scale tuning, calibration, and production quality SLOs |
| AI Gateway | **2.5** | Entra JWT, trusted claims, redaction, model-routing and budget contracts | rate/concurrency enforcement, Graph resolver, deployment hardening, and real proof |
| Service/resource intelligence graph | **3.0** | topology/service/API/data/queue/owner/SLO projections | automated runtime/IaC discovery and organization-scale evidence |
| PR Guardian | **3.0** | GitHub event -> diff -> topology/risk -> shadow workflow -> neutral check/comment plus explicit reviewer-label closure record | durable finding/evidence/outcome store, independent post-merge correlation, precision/recall calibration, and governed enforcement decision |
| Architecture Guard | **2.5** | deterministic ADR/reference rules and reviewable SDLC result | broader rule library, live publishing, waiver governance, and outcomes |
| Deployment Failure Investigator | **2.5** | pipeline-failure evidence/last-good correlation and workflow | provider breadth, richer logs/timeline UX, and calibration |
| Incident Intelligence | **3.0** | Azure Monitor/App Insights/OTel/K8s adapters and correlation primitives | real incident-system publishing, richer queries, and outcome calibration |
| Drift Detector | **2.5** | desired-vs-observed model and durable finding | wider resource coverage, corrective workflow, and precision measurement |
| Knowledge Decay | **2.5** | stale/ownerless/conflicting detection and maintenance plan | live publisher, resolution tracking, and freshness SLOs |
| Predictive / change-risk intelligence | **2.5** | explainable scoring and feedback-safe calibration primitives | real historical features, service calibration, and false-negative monitoring |
| Engineering Portal / service intelligence | **2.5** | service/portfolio view models and API reference paths | authenticated UI/API deployment, navigation, and operator workflows |
| Feedback learning | **2.5** | explicit reviewer-label shadow outcomes, durable outcome model, and conservative precision/acceptance metrics | retained independent outcome correlation, cohort analysis, and repository-specific calibration |
| Executive Control Tower | **2.5** | modeled engineering/remediation/cost/feedback views | live trend API/dashboard, source lineage, and benefit governance |
| Authoritative state | **3.0** | Cosmos adapter with storage-level CAS plus canonical atomic lifecycle receipts, idempotency, cancellation, and restart coverage | provision/wire state, multi-region ops, backup/restore, retention evidence |
| Durable orchestration | **3.0** | local leases/retries/recovery/DLQ plus fail-closed lifecycle/audit activity bridge and evidence-only Temporal worker | registered product workflows, production queue/backend, and concurrency/compensation operations |
| OPA mutation authorization | **3.0** | fail-closed contract, native policy CI, and local parity controls | bundle promotion/version operations and production policy SLO evidence |
| Human approval | **2.5** | exact-plan-bound, expiring approval and identity boundary | role-mapped approval UX, delegated governance, and operational evidence |
| Certified runbook library / AKS actions | **3.0** | typed failure classes, pre/postconditions, argv-only actions, live preflight | broader catalog and repeated production-like exercises |
| Digital twin | **3.0** | isolated ephemeral K8s sandbox, stripped identity, same action/verification, cleanup | dependency/data fixtures, traffic replay, and fidelity evidence |
| Supervised self-healing L3 implementation | **3.0** | evidence -> plan -> approval -> OPA -> twin -> action -> verify -> rollback/escalate -> audit path | managed production dependencies and retained real service/environment/runbook drills |
| L3 operational certification | **2.0** | certification/evidence framework and exercise taxonomy | execute/retain required drills on real candidate services |
| L4 bounded autonomy | **1.5** | service/environment/runbook-scoped model and promotion rules | L3 evidence, chaos history, error-budget and kill-switch proof |
| Control-plane observability | **3.0** | correlated traces/metrics and SLO projection primitives | dashboards, paging thresholds, trace-to-audit reconciliation, and production history |
| AI security / red team | **3.0** | poisoned-evidence, ACL-isolation, confused-deputy and policy-bypass CI corpus | larger indirect injection/egress/identity corpus and live exercises |
| Software supply chain | **2.0** | exact dependency pins, red-team gate, and CycloneDX SBOM generated from the built image | registry-backed signed attestations and cluster admission enforcement |
| FinOps / AI economics | **2.5** | attributed model/search/tool cost primitives and budget contracts | live optimization, forecasts, quota enforcement, and service budget policy |
| Cross-cloud portability | **2.0** | provider abstraction contracts | deliberately defer implementation depth until Azure path is production-proven |

## Balance check

Layer maturity is the arithmetic mean of the capability rows listed for it, recomputed whenever a
row changes. The membership is the mapping; there is no separately asserted layer score.

| Layer | Capability rows | Mean |
|---|---|---:|
| Organizational Knowledge / RAG | Code ingestion, Organizational engineering memory, Hybrid/vector RAG, AI Gateway | **2.8** |
| Developer & SDLC Intelligence | Service/resource intelligence graph, PR Guardian, Architecture Guard, Predictive / change-risk intelligence, Knowledge Decay | **2.7** |
| Operational Intelligence | Deployment Failure Investigator, Incident Intelligence, Drift Detector | **2.7** |
| Portal / Feedback / Executive UX | Engineering Portal / service intelligence, Feedback learning, Executive Control Tower | **2.5** |
| Control Plane / Safety | Authoritative state, Durable orchestration, OPA mutation authorization, Human approval, Control-plane observability, AI security / red team, Software supply chain | **2.8** |
| Self-Healing Mechanics | Certified runbook library / AKS actions, Digital twin, Supervised self-healing L3 implementation | **3.0** |
| Operational L3 Certification | L3 operational certification | **2.0** |
| Bounded L4 Autonomy | L4 bounded autonomy | **1.5** |
| Foundations (not a product layer) | Architecture coherence / governance, Secure Azure foundation, FinOps / AI economics, Cross-cloud portability | **2.6** |

The control-plane mechanics are intentionally ahead of L4 certification, but no layer is
production-capable until its applicable NFRs and retained evidence are satisfied. Future work
must not increase L4 depth while the upper product layers lack measured outcomes.

## Grooming guardrails

1. **Original architecture first.** Every PR names the original capability it advances.
2. **No autonomy-first drift.** Do not add new L4 machinery while Organizational Knowledge, SDLC Intelligence, Operational Intelligence, Portal/Feedback or Executive UX is below 4.0 unless required for a critical safety defect.
3. **Evidence beats maturity claims.** Reference implementations do not count as production-proven.
4. **Feedback cannot weaken authorization.** Learned thresholds may improve ranking/risk bands; they cannot change ACL or OPA mutation rights.
5. **Measured vs modeled stays explicit.** Board/ROI metrics carry source and basis lineage.
6. **Human authority remains for high blast radius.** L5 unrestricted autonomy remains unsupported.

## Next execution queue

Sequencing is owned by the roadmap stages in
[`../roadmap/technical-roadmap-24-months.md`](../roadmap/technical-roadmap-24-months.md); this
scorecard no longer keeps a competing queue. The capability rows above map to those stages as
follows:

| Roadmap stage | Capability rows it advances |
|---|---|
| Stage 0 — product truth and pilot foundation | Architecture coherence / governance, Software supply chain |
| Stage 1 — pilot-ready shadow PR Guardian | PR Guardian, Feedback learning, Predictive / change-risk intelligence |
| Stage 2 — measured advisory decision | Code ingestion, Hybrid/vector RAG, AI Gateway, Secure Azure foundation, Authoritative state |
| Stage 3 — PR Intelligence V2 and Architecture Guard | Architecture Guard, Knowledge Decay, Service/resource intelligence graph, Engineering Portal |
| Stage 4 — operations intelligence at L1/L2 | Incident Intelligence, Deployment Failure Investigator, Drift Detector, Executive Control Tower, Control-plane observability |
| Stage 5 — rehearsed remediation and narrow L3 candidates | Durable orchestration, OPA mutation authorization, Human approval, Certified runbook library, Digital twin, Supervised self-healing L3, L3 operational certification |
| Stage 6 — bounded L4 autonomy | L4 bounded autonomy (only after Stage 5 evidence; guardrail 2 above still applies) |
