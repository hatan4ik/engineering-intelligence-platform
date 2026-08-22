# Engineering Intelligence Platform — Original Architecture Maturity Scorecard

This scorecard prevents implementation drift. It measures the repository against the **original Engineering Intelligence Platform architecture**, not against the amount of code in any one subsystem.

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
| Architecture coherence / governance | **4.5** | north-star, ADR invariants, capability reconciliation, L0–L4 boundary | validate against real operating model over time |
| Secure Azure foundation | **4.0** | private AI/Search/Key Vault, Private Link/DNS, AKS Workload Identity | production ingress/egress, scale and DR exercises |
| Code ingestion | **3.5** | GitHub/ADO events, AST chunks, ACL metadata, ledger/DLQ/replay | shared durable queue, backpressure, large-scale reconciliation |
| Organizational engineering memory | **3.5** | Boards, Jira, Confluence adapters; governed decision-conversation ingestion | live enterprise credentials/sync, broader ACL resolution, source SLAs |
| Hybrid/vector RAG | **4.0** | vector/hybrid retrieval, ACL trimming, citations/eval | corpus-scale tuning, reranking/calibration, production quality SLOs |
| AI Gateway | **4.0** | Entra JWT, trusted claims, redaction, model routing and budgets | Graph overage resolver, quotas/cache/operator UX |
| Service/resource intelligence graph | **4.0** | persistent topology plus service/API/data/queue/owner/SLO projections | automated runtime/IaC discovery at organization scale |
| PR Guardian | **4.0** | live GitHub event -> diff -> topology/risk -> durable workflow -> Check/comment | measured precision/recall and threshold calibration from real history |
| Architecture Guard | **3.5** | deterministic ADR/reference rules and reviewable SDLC result | broader rule library + live PR publishing/waiver governance |
| Deployment Failure Investigator | **3.5** | pipeline failure evidence/last-good correlation and durable workflow | provider breadth, richer logs/timeline UX and calibration |
| Incident Intelligence | **4.0** | Azure Monitor, App Insights, OTel, K8s evidence, topology/change correlation, operator timeline | real incident-system publishing, richer trace/log queries, outcome calibration |
| Drift Detector | **3.5** | Git/Terraform desired vs Azure Resource Graph observed | corrective PR automation, more Azure resource types, drift precision metrics |
| Knowledge Decay | **3.5** | stale/ownerless/conflicting detection -> reviewable maintenance plan | live publisher, resolution tracking and freshness SLOs |
| Predictive / change-risk intelligence | **3.5** | explainable scoring, historical probability model, feedback-safe calibration | real feature history, service-specific calibration, monitored false-negative rate |
| Engineering Portal / service intelligence | **3.5** | unified service view: topology, SLO, risk, knowledge, architecture, incidents, feedback | authenticated API/UI, drill-down/navigation, operator workflows |
| Feedback learning | **3.5** | durable accepted/rejected/reverted/correct/incorrect outcomes + precision/acceptance metrics | automatic outcome capture from PR/deploy/incident systems; cohort analysis |
| Executive Control Tower | **3.5** | engineering/remediation/cost/feedback view with measured-vs-derived-vs-modeled lineage | live dashboard/API, trend windows, source lineage links and benefit governance |
| Authoritative state | **4.0** | Cosmos adapter with storage-level CAS + local contract | multi-region ops, backup/restore, retention evidence |
| Durable orchestration | **3.5** | leases, retries, recovery, DLQ, durable remediation jobs | production queue/backend and concurrency/compensation operations |
| OPA mutation authorization | **4.5** | authoritative contract, fail-closed client, native policy CI | bundle promotion/version ops and production policy SLO evidence |
| Human approval | **3.5** | exact-plan bound, expiring approval and Entra boundary | role-mapped portal/Teams/Slack UX and delegated approval governance |
| Certified runbook library / AKS actions | **3.5** | typed failure classes, pre/postconditions, argv-only actions, live preflight | broader AKS/Azure catalog + repeated production-like exercises |
| Digital twin | **3.5** | isolated ephemeral K8s sandbox, stripped prod identity, same action/verification, cleanup | dependency/data fixtures, traffic replay and environment fidelity |
| Supervised self-healing L3 implementation | **4.0** | evidence -> plan -> approval -> OPA -> twin -> action -> verify -> rollback/escalate -> audit | retained real service/environment/runbook exercise evidence |
| L3 operational certification | **2.5** | certification/evidence framework and required exercise taxonomy | execute/retain required drills on real candidate services |
| L4 bounded autonomy | **2.0** | service/environment/runbook-scoped model and strict promotion gates | L3 production evidence, chaos history, error-budget and kill-switch proof |
| Control-plane observability | **4.0** | correlated traces/metrics and SLO projection across approval/action/verification | dashboards, paging thresholds and production SLO history |
| AI security / red team | **3.5** | poisoned evidence, ACL isolation, confused deputy and policy-bypass CI corpus | larger indirect injection/egress/identity attack corpus and exercises |
| Software supply chain | **3.0** | SBOM, provenance digest and fail-closed admission verifier | signed/keyless attestations and cluster admission enforcement |
| FinOps / AI economics | **3.5** | attributed model/search/tool costs, budgets, anomalies, OTel cost metrics | live optimization loop, forecasts and service budget policy |
| Cross-cloud portability | **2.5** | provider abstraction contracts | deliberately defer implementation depth until Azure path is production-proven |

## Balance check

Approximate product maturity by architectural layer:

```text
Organizational Knowledge / RAG        3.8 / 5
Developer & SDLC Intelligence         3.8 / 5
Operational Intelligence              3.8 / 5
Portal / Feedback / Executive UX      3.5 / 5
Control Plane / Safety                 4.1 / 5
Self-Healing Mechanics                 3.8 / 5
Operational L3 Certification           2.5 / 5
Bounded L4 Autonomy                    2.0 / 5
```

The control plane is intentionally more mature than L4 certification, but future work must not increase L4 depth while the upper product layers lag materially behind.

## Grooming guardrails

1. **Original architecture first.** Every PR names the original capability it advances.
2. **No autonomy-first drift.** Do not add new L4 machinery while Organizational Knowledge, SDLC Intelligence, Operational Intelligence, Portal/Feedback or Executive UX is below 4.0 unless required for a critical safety defect.
3. **Evidence beats maturity claims.** Reference implementations do not count as production-proven.
4. **Feedback cannot weaken authorization.** Learned thresholds may improve ranking/risk bands; they cannot change ACL or OPA mutation rights.
5. **Measured vs modeled stays explicit.** Board/ROI metrics carry source and basis lineage.
6. **Human authority remains for high blast radius.** L5 unrestricted autonomy remains unsupported.

## Next balanced execution queue

1. **PR Guardian / Predictive Risk 2.1:** connect real feedback outcomes to service-specific calibration and monitored false-negative rates.
2. **Architecture Guard 2.1:** GitHub/ADO publisher, ADR provenance links, reviewed waivers and expiry.
3. **Knowledge Decay 2.1:** publish maintenance PRs/tickets and track resolution/freshness SLOs.
4. **Engineering Portal 2.1:** authenticated API/UI combining service intelligence and evidence drill-down.
5. **Incident Intelligence 2.1:** incident-system publisher and feedback capture from confirmed RCA.
6. **Drift 2.1:** corrective PR generation and measured false-positive rates.
7. **Control Tower 2.1:** time-series/trend API and source-lineage drill-down.
8. **Only after upper layers are ~4.0:** execute retained L3 certification exercises; then evaluate narrowly scoped L4 promotion candidates.
