# Engineering Intelligence Platform

[![CI](https://github.com/hatan4ik/engineering-intelligence-platform/actions/workflows/ci.yml/badge.svg)](https://github.com/hatan4ik/engineering-intelligence-platform/actions/workflows/ci.yml)
[![PR Guardian](https://github.com/hatan4ik/engineering-intelligence-platform/actions/workflows/pr-guardian.yml/badge.svg)](https://github.com/hatan4ik/engineering-intelligence-platform/actions/workflows/pr-guardian.yml)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](app/requirements.txt)
[![License: LGPL-2.1](https://img.shields.io/badge/license-LGPL--2.1-green.svg)](LICENSE)

**Company Brain** is the product built in this repository: a governed intelligence layer for the
SDLC. Repositories, work items, ADRs, runbooks, CI/CD history, and operational telemetry become
**evidence-backed, ACL-trimmed answers and recommendations** — and, for certified failure classes,
**supervised self-healing** on Azure/AKS.

> **The invariant:** AI reasons and recommends → identity and ACLs constrain evidence →
> deterministic policy authorizes → allow-listed runbooks execute → independent signals
> verify → rollback/escalation closes the loop. L5 unrestricted autonomy is out of scope
> by design.

**Status:** working reference implementation plus target-state architecture — not yet a
production-ready autonomous control plane. “Implemented” means an executable, CI-covered
reference path unless an environment-scoped evidence record says otherwise; it does not mean
production-certified. [Current Position](docs/CURRENT-POSITION.md) is the authoritative answer
to what is true today.

The current product wedge is **PR Guardian**: evidence-backed, initially non-blocking pull
request intelligence for one or two Azure engineering repositories. See
[`docs/PRODUCT-STRATEGY.md`](docs/PRODUCT-STRATEGY.md). Detailed source capability assessment is
in [`architecture/CAPABILITY-RECONCILIATION.md`](architecture/CAPABILITY-RECONCILIATION.md), and
production claims require retained evidence under
[`docs/PRODUCTION-EVIDENCE.md`](docs/PRODUCTION-EVIDENCE.md).

## Contents

- [Architecture at a glance](#architecture-at-a-glance)
- [Quick start](#quick-start)
- [Azure-backed mode](#azure-backed-mode)
- [Current scope and limits](#current-scope-and-limits)
- [Documentation](#documentation)
- [Repository map](#repository-map)
- [Development](#development)
- [Capability progression](#capability-progression)

## Architecture at a glance

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/diagrams/readme-overview-dark.svg">
    <img alt="The platform at a glance: sources to Azure through knowledge, gateway, agents, control and execution, with verification and telemetry feeding back" src="docs/diagrams/readme-overview-light.svg" width="940">
  </picture>
</p>

Full design with per-plane diagrams, data model, failure modes, and alternatives considered:
**[`architecture/design.md`](architecture/design.md)**.

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

Run the repository reference checks that CI runs:

```bash
pip install -r requirements/test.txt -r requirements/dev.txt -r requirements/build.txt
pytest -q
python -m eval.evaluate
python -m demo.aks.scenario_runner
terraform -chdir=infra/terraform init -backend=false && terraform -chdir=infra/terraform validate
helm lint helm/eip --values helm/eip/values.ci.yaml
docker build -t eip:local .
```

These checks establish code and configuration consistency. They do not establish a production
deployment, real-data isolation, recovery behavior, or autonomous-remediation readiness.

## Azure-backed mode

Set `EIP_BACKEND=azure` plus:

| Variable | Purpose |
|---|---|
| `AZURE_SEARCH_ENDPOINT`, `AZURE_SEARCH_INDEX` | ACL-trimmed retrieval |
| `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_CHAT_DEPLOYMENT` | Grounded synthesis |
| `EIP_GITHUB_WEBHOOK_SECRET` | PR Guardian webhook ingress (HMAC, fail closed) |

Azure service clients use `DefaultAzureCredential` (Managed Identity in-cluster). Callers of the
gateway use an Entra access token or configured API-key principal; request headers are a
deterministic-demo affordance only and are never trusted with the Azure backend. ACL filtering is
compiled into every search request **before** any content reaches the model.

An Azure-backed request path is a reference integration until its identity, private network,
state/audit, quality, and operational evidence has been retained for a named environment. See
[`docs/PRODUCTION-EVIDENCE.md`](docs/PRODUCTION-EVIDENCE.md) and
[`architecture/non-functional-requirements.md`](architecture/non-functional-requirements.md).

The Helm chart deliberately refuses its default values. A deployment must provide a reviewed
values file with a digest-pinned image, Workload Identity client ID, Entra tenant/audience, and
Azure Search/OpenAI configuration; it cannot deploy the deterministic header-identity demo.
Terraform likewise requires an explicit location, environment classification, and Entra AKS admin
group. [`infra/terraform/terraform.tfvars.example`](infra/terraform/terraform.tfvars.example)
is a placeholder-only starting point, not an apply authorization.

For the durable control plane, the selected integration path is Temporal on private AKS with
private PostgreSQL. Its chart has separate fail-closed defaults and requires an existing secret;
it does not run schema migrations or create database users during a normal server release. See
[`architecture/adr/001-temporal-control-plane.md`](architecture/adr/001-temporal-control-plane.md).
The image also contains an mTLS-only, non-consequential Temporal evidence worker; see
[`docs/TEMPORAL-WORKER-RUNBOOK.md`](docs/TEMPORAL-WORKER-RUNBOOK.md). It is not yet the
authoritative state/audit or remediation execution path.

## Current scope and limits

| Available reference capability | Not yet a production claim |
|---|---|
| Local deterministic query demo; Azure retrieval/gateway adapters; GitHub PR Guardian workflow; policy/runbook and digital-twin reference paths | A released production container/chart, calibrated retrieval or PR-risk quality, real-data production proof, managed durable queue/audit export, or L3/L4 certification |
| PR Guardian is the first product surface; it starts as shadow-only, evidence-backed feedback | General engineering chat, enterprise-wide source rollout, advisory/enforcement without evidence review, and production self-healing |

The exact current position, owner, and remaining external gates are in
[`docs/CURRENT-POSITION.md`](docs/CURRENT-POSITION.md). The
[`architecture/CAPABILITY-RECONCILIATION.md`](architecture/CAPABILITY-RECONCILIATION.md) provides
the capability-by-capability source assessment. Do not infer deployment readiness from a demo,
test, or maturity score.

## Documentation

Use the [Company Brain Documentation portal](docs/README.md) for role-based reading paths and
the [Documentation Governance and Register](docs/DOCUMENT-STATUS.md) for the authoritative
source, lifecycle, and owner of every maintained document. This README intentionally stays a
concise repository entry point rather than duplicating the portal.

## Repository map

| Path | Responsibility | Contents |
|---|---|---|
| `app/` | Gateway | FastAPI composition, query API, webhook ingress, operational routes, Azure RAG adapter, and telemetry bootstrap |
| `company_brain/` | Company Brain | Canonical organizational facts, evidence pointers, provenance, durable projections, and qualified world-model reads; never action authority |
| `ingestion/` | Knowledge | Source events, AST/text chunking, ACLs, index adapters, ledger/DLQ/replay, and embedding contracts |
| `intelligence/` | Reasoning | Change risk, PR Guardian analysis, incidents, deployments, drift, SLO context, and calibration |
| `topology/` | Company Brain graph | Service/resource projections and blast-radius traversal over the engineering topology |
| `product/` | Product workflows | PR Guardian and incident, deployment, drift, knowledge-maintenance, and self-healing service orchestration |
| `integrations/` | Edge adapters | GitHub, Azure, Azure DevOps, and Azure Monitor translation layers; no product-policy ownership |
| `feedback/` | Learning loop | Durable reviewer/outcome capture and shadow-pilot calibration reports |
| `control_plane/` | Control | Workflow state-machine contracts, approval boundaries, and remediation coordination |
| `state/` | Durable records | Lifecycle, audit, idempotency, and reference state-store adapters |
| `orchestration/` | Durable execution | Temporal worker/client/workflow integration and reference job scheduling |
| `remediation/` | Execution | Runbook catalog, deterministic/OPA policy, Kubernetes adapter, simulation, verification, and rollback |
| `resilience/` | Autonomy assurance | Certification scope, exercise, and degraded-mode contracts |
| `security/` | Security controls | Adversarial-input, provenance, and red-team checks |
| `telemetry/` | Observability | Operation events, OTEL wiring, and control-plane telemetry contracts |
| `finops/` | Economics | Cost attribution, outcome accounting, rate contracts, and control-tower metrics |
| `portal/` | Presentation | Read-model/view contracts for operational and portfolio control towers |
| `eval/` | Quality | Retrieval evaluation harness |
| `validation/` | Evidence validation | Evidence registry, integration probes, soak checks, readiness evaluation, and deferred Temporal probes |
| `supply_chain/` | Delivery integrity | Dependency, SBOM, and image-evidence verification used by CI |
| `scripts/` | Operator tools | Versioned, reviewable maintenance, investigation, certification, and validation entry points |
| `infra/` | Infrastructure | Terraform Azure baseline/private AI foundation and OPA policy bundle |
| `helm/eip/` · `helm/temporal/` · `Dockerfile` | Deploy | Fail-closed API chart, pinned Temporal wrapper, and container image |
| `demo/aks/` | Demo | Fault/remediation scenario runner |
| `architecture/` · `docs/` · `governance/` · `roadmap/` | Product knowledge | Design decisions, evidence rules, operating model, and outcome-gated delivery plan |
| `slides/` | Program communication | Board-deck generator and source material |

## Version semantics

The Python package's `[project].version` is the application contract version. The EIP Helm
chart's `version` is the independently versioned chart package: change it when chart templates,
defaults, or dependencies change. Its `appVersion` identifies the application contract the chart
deploys and must match `[project].version`; the repository test enforces that relationship.

Neither version authorizes a deployment. A reviewed, digest-pinned image is the runtime identity;
the chart version and application version make that identity intelligible in release records. The
Temporal chart's `appVersion` names the external Temporal server and is intentionally independent
of the EIP application version.

## Development

```bash
pytest -q  # contracts, durability, composition, API, and policy tests
```

- CI (`.github/workflows/ci.yml`) gates reference checks: tests, evaluation harness, scenario
  runner, Terraform fmt/validate, Helm lint, an SBOM generated from the built image, and container
  smoke tests. The resulting local CI evidence is **not** a signed deployment attestation; registry
  attestation and admission enforcement are required before a production promotion.
- **PR Guardian is a shadow pilot, not a merge gate**: the pull-request workflow evaluates the
  diff with a read-only token and publishes a separate `neutral` advisory check only through a
  trusted default-branch workflow. Closed PRs can capture explicit reviewer labels for calibration.
  See [the shadow-pilot runbook](docs/PR-GUARDIAN-SHADOW-PILOT.md); no pilot evidence is collected
  or claimed by this repository alone.
- Every PR must map to a capability in the
  [reconciliation](architecture/CAPABILITY-RECONCILIATION.md) and improve a measurable
  outcome.

## Capability progression

These are the target product capabilities, not a second delivery sequence. The
[outcome-gated roadmap](roadmap/technical-roadmap-24-months.md) is the authoritative ordering and
requires evidence at every promotion gate.

1. **Engineering Knowledge** — secure, ACL-aware organizational memory and evidence-backed RAG
2. **AI-native SDLC** — PR Guardian, Architecture Guard, deployment intelligence
3. **Operational Intelligence** — incident correlation, drift detection, SLO-aware RCA
4. **Predictive Engineering** — explainable change/deployment risk from graph + history
5. **Supervised Self-Healing** — policy, approvals, certified runbooks, verification, rollback
6. **Bounded Autonomy** — L4 only per service/environment/runbook, after exercised evidence
