# Engineering Intelligence Platform

[![CI](https://github.com/hatan4ik/engineering-intelligence-platform/actions/workflows/ci.yml/badge.svg)](https://github.com/hatan4ik/engineering-intelligence-platform/actions/workflows/ci.yml)
[![PR Guardian](https://github.com/hatan4ik/engineering-intelligence-platform/actions/workflows/pr-guardian.yml/badge.svg)](https://github.com/hatan4ik/engineering-intelligence-platform/actions/workflows/pr-guardian.yml)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](app/requirements.txt)
[![License: LGPL-2.1](https://img.shields.io/badge/license-LGPL--2.1-green.svg)](LICENSE)

A governed intelligence layer for the SDLC: repositories, work items, ADRs, runbooks, CI/CD
history, and operational telemetry become **evidence-backed, ACL-trimmed answers and
recommendations** — and, for certified failure classes, **supervised self-healing** on
Azure/AKS.

> **The invariant:** AI reasons and recommends → identity and ACLs constrain evidence →
> deterministic policy authorizes → allow-listed runbooks execute → independent signals
> verify → rollback/escalation closes the loop. L5 unrestricted autonomy is out of scope
> by design.

**Status:** working reference implementation plus target-state architecture — not yet a
production-ready autonomous control plane.
[`architecture/CAPABILITY-RECONCILIATION.md`](architecture/CAPABILITY-RECONCILIATION.md)
grades every capability (Implemented / Partial / Skeleton / Missing) and owns the execution
queue.

## Contents

- [Architecture at a glance](#architecture-at-a-glance)
- [Quick start](#quick-start)
- [Azure-backed mode](#azure-backed-mode)
- [Documentation](#documentation)
- [Repository map](#repository-map)
- [Development](#development)
- [Transformation path](#transformation-path)

## Architecture at a glance

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/diagrams/readme-overview-dark.svg">
    <img alt="The platform at a glance: sources to Azure through knowledge, gateway, agents, control and execution, with verification and telemetry feeding back" src="docs/diagrams/readme-overview-light.svg" width="940">
  </picture>
</p>

Full design with per-plane diagrams, data model, failure modes, and alternatives considered:
**[`architecture/DESIGN.md`](architecture/DESIGN.md)**.

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r app/requirements.txt
uvicorn app.main:app --reload
```

Query the local deterministic backend (no cloud dependency):

```bash
curl -s http://127.0.0.1:8000/v1/query \
  -H 'content-type: application/json' \
  -H 'x-eip-groups: engineering' \
  -d '{"question":"How should production remediation work?"}'
```

Run the full local validation that CI runs:

```bash
pytest -q
python eval/evaluate.py
python demo/aks/scenario_runner.py
terraform -chdir=infra/terraform init -backend=false && terraform -chdir=infra/terraform validate
helm lint helm/eip
docker build -t eip:local .
```

## Azure-backed mode

Set `EIP_BACKEND=azure` plus:

| Variable | Purpose |
|---|---|
| `AZURE_SEARCH_ENDPOINT`, `AZURE_SEARCH_INDEX` | ACL-trimmed retrieval |
| `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_CHAT_DEPLOYMENT` | Grounded synthesis |
| `EIP_GITHUB_WEBHOOK_SECRET` | PR Guardian webhook ingress (HMAC, fail closed) |

Authentication uses `DefaultAzureCredential` (Managed Identity in-cluster). ACL filtering is
compiled into every search request **before** any content reaches the model. Production
hardening still required — Entra-backed API identity, controlled egress, production state
adapters — is tracked as explicit capability gaps, not implied to exist.

## Documentation

Suggested reading order within each audience.

### Start here

| Document | What it is |
|---|---|
| [`architecture/DESIGN.md`](architecture/DESIGN.md) | **System design** — goals/non-goals, per-plane detailed design, security model, data model, failure modes, alternatives considered |
| [`architecture/CAPABILITY-RECONCILIATION.md`](architecture/CAPABILITY-RECONCILIATION.md) | **Execution source of truth** — capability status matrix and the product implementation queue |
| [`governance/security-threat-model.md`](governance/security-threat-model.md) | Threats, required controls, and the L0–L5 autonomy tiers |

### Engineering deep dives

| Document | What it is |
|---|---|
| [`docs/INGESTION.md`](docs/INGESTION.md) | Ingestion flow, chunk/document identity, idempotency and reconciliation |
| [`architecture/m3-production-ingestion.md`](architecture/m3-production-ingestion.md) | Production ingestion design (ledger, DLQ, loaders, ACL propagation) |
| [`architecture/organizational-memory.md`](architecture/organizational-memory.md) | Work items, docs, incidents, and conversations as governed knowledge |
| [`architecture/authoritative-state.md`](architecture/authoritative-state.md) | State store, optimistic concurrency, and the hash-chained audit log |
| [`architecture/durable-orchestration.md`](architecture/durable-orchestration.md) | Job queue leases, retry/backoff, DLQ, and crash recovery |
| [`architecture/azure-devops-self-healing-reference.md`](architecture/azure-devops-self-healing-reference.md) | Target-state Azure/ADO/AKS closed-loop reference |
| [`architecture/p1-secure-azure-foundation.md`](architecture/p1-secure-azure-foundation.md) | Private endpoints, Workload Identity, private DNS foundation |
| [`architecture/runtime-observability.md`](architecture/runtime-observability.md) | Operation telemetry and FinOps contract |
| [`architecture/l4-certification.md`](architecture/l4-certification.md) | Evidence-based bounded-autonomy certification |
| [`architecture/vertical-slice.md`](architecture/vertical-slice.md) | The original end-to-end demo slice and its security invariants |
| [`architecture/adr/`](architecture/adr) | Architecture decision records |
| [`docs/PRODUCTION-READINESS.md`](docs/PRODUCTION-READINESS.md) | Promotion gates: functional, security, reliability, operational safety, economics |

### Program and executive

| Document | What it is |
|---|---|
| [`docs/executive-memo.md`](docs/executive-memo.md) | The decision memo: problem, program, guardrails |
| [`docs/board-deck-narrative.md`](docs/board-deck-narrative.md) | 12-slide board narrative (generator in `slides/`) |
| [`docs/kpi-system.md`](docs/kpi-system.md) | Engineering, AI-quality, safety, and FinOps KPIs |
| [`finops/cfo-roi-model.md`](finops/cfo-roi-model.md) | Value equation, cost buckets, investment gates |
| [`roadmap/technical-roadmap-24-months.md`](roadmap/technical-roadmap-24-months.md) | Phased 18–24-month roadmap |
| [`roadmap/PROGRAM-BACKLOG.md`](roadmap/PROGRAM-BACKLOG.md) | A–Z program backlog |
| [`governance/operating-model.md`](governance/operating-model.md) | Ownership, council, release gates, decision rights |

### Historical reviews

| Document | What it is |
|---|---|
| [`architecture/ALIGNMENT-REVIEW.md`](architecture/ALIGNMENT-REVIEW.md) | Structural gap audit that motivated the corrective P-slices |
| [`docs/architecture-review-2026-08.md`](docs/architecture-review-2026-08.md) | Point-in-time implementation review (pre-corrective baseline) |

## Repository map

| Path | Plane | Contents |
|---|---|---|
| `ingestion/` | Knowledge | Source events, AST/text chunking, ACLs, index adapters, ledger/DLQ/replay, embedding contract |
| `app/` | Gateway | FastAPI API, Azure RAG backend, webhook ingress, OTel bootstrap |
| `intelligence/` | Intelligence | Service graph, change risk, PR Guardian, incident/deployment/drift analysis, SLO context |
| `product/` `integrations/` `scripts/` | Intelligence | PR Guardian E2E: product service, GitHub REST/webhook adapters, CI runner |
| `control_plane/` `state/` `orchestration/` | Control | Durable workflows, authoritative state + audit chain, job queue, plan-bound approvals |
| `remediation/` | Execution | Runbook catalog, deterministic policy, Kubernetes adapter, simulation, verify/rollback |
| `security/` `resilience/` | Control | Adversarial/provenance controls, degraded-mode policy, L4 certification |
| `telemetry/` `finops/` `portal/` | Observability | Operation events, cost attribution/outcomes, control-tower view models |
| `eval/` | Quality | Retrieval evaluation harness |
| `infra/` | Infra | Terraform (Azure baseline + private AI foundation), OPA policy examples |
| `helm/eip/` · `Dockerfile` | Deploy | AKS chart and container image |
| `demo/aks/` | Demo | Fault/remediation scenario runner |
| `providers/` | Portability | Cloud-neutral provider contracts |
| `slides/` | Program | Board-deck generator |
| `src/` | Legacy | Early prototypes retained for reference |

## Development

```bash
pytest -q            # contracts, durability, composition, API, and policy tests
python -m pyflakes . # lint
```

- CI (`.github/workflows/ci.yml`) gates every PR: tests, evaluation, scenario runner,
  Terraform fmt/validate, Helm lint, container build.
- **The repository reviews itself**: `.github/workflows/pr-guardian.yml` runs the PR
  Guardian on every pull request — diff → service graph → deterministic risk → durable
  workflow with verified audit chain → evidence comment on the PR.
- Every PR must map to a capability in the
  [reconciliation](architecture/CAPABILITY-RECONCILIATION.md) and improve a measurable
  outcome.

## Transformation path

1. **Engineering Knowledge** — secure, ACL-aware organizational memory and evidence-backed RAG
2. **AI-native SDLC** — PR Guardian, Architecture Guard, deployment intelligence
3. **Operational Intelligence** — incident correlation, drift detection, SLO-aware RCA
4. **Predictive Engineering** — explainable change/deployment risk from graph + history
5. **Supervised Self-Healing** — policy, approvals, certified runbooks, verification, rollback
6. **Bounded Autonomy** — L4 only per service/environment/runbook, after exercised evidence
