# 18–24 Month Technical Roadmap

## Phase 0 — Foundation (Months 0–2)
Build secure model access, AI Gateway/RAG orchestration, hybrid search, metadata store, private networking, identity, token/cost telemetry and retrieval evaluation.

**Exit:** 2–3 repos indexed, citation-backed answers, RBAC enforced, cost/query measurable.

## Phase 1 — Knowledge Layer (Months 3–5)
Scale ingestion across repositories, Boards/Jira, ADRs, runbooks and CI/CD history. Add commit-aware incremental indexing, ownership metadata and IDE/developer integration.

**Exit:** internal engineering questions are answered from governed sources without tribal-knowledge archaeology.

## Phase 2 — PR Intelligence (Months 6–8)
Deploy PR Guardian for secure-coding patterns, IaC rules, architecture constraints, similar regressions, ownership context and change-impact hints.

**Exit:** useful PR feedback with measured precision and false-positive rate.

## Phase 3 — Incident Intelligence (Months 9–12)
Integrate Azure Monitor, Log Analytics, App Insights, Kubernetes events, OpenTelemetry and deployment history. Build failure investigator and incident summarizer.

**Exit:** evidence-backed probable cause and runbook recommendation within minutes.

## Phase 4 — Predictive Release Governance (Months 12–16)
Score changes by diff size, infra touchpoints, service criticality, historical failure similarity, blast radius, test coverage and dependency graph.

**Exit:** deployment gates and test depth adapt to measured change risk.

## Phase 5 — Guardrailed Self-Healing (Months 16–24)
Introduce drift detection, allow-listed runbooks, policy evaluation, non-prod autonomous execution, production approval tiers, automated rollback, verification loops and corrective PR generation.

**Exit:** selected known failure classes are detected, safely remediated, verified and documented automatically.

## Program gates
- No autonomous production mutation before retrieval/evaluation quality is proven.
- No runbook enters autonomous mode without idempotency, rollback and bounded blast radius.
- Each phase requires KPI improvement and security sign-off before expansion.