# Company Brain — A–Z Capability Catalogue

| | |
|---|---|
| **Classification** | Target proposal — workstream catalogue, not a second delivery sequence |
| **Owner** | Platform Engineering |
| **Reviewed** | 2026-09-03 |
| **Assertions are** | planning themes; sequencing is owned only by the outcome-gated roadmap |
| **Authoritative current state** | [`CURRENT-POSITION.md`](../docs/CURRENT-POSITION.md) |
| **Delivery sequence** | [`technical-roadmap-24-months.md`](technical-roadmap-24-months.md) |


This catalogue turns the Company Brain target architecture into a set of legible workstreams. It
is not a second roadmap: its alphabetical labels do not establish priority, commitment, or order.
The outcome-gated roadmap is the sole delivery sequence.

## North-star architecture

`Events -> Ingestion -> Knowledge/Graph -> Intelligence Agents -> Policy -> Action -> Verification -> Learning/Audit`

The LLM is never the authorization boundary. Identity, ACLs, policy-as-code, blast-radius controls, deterministic runbooks, verification and kill switches remain authoritative.

## A–Z workstreams

| ID | Workstream | Core outcome | Exit criteria |
|---|---|---|---|
| A | Architecture & ADRs | Versioned target architecture and decisions | C4 views + ADR process + ownership |
| B | Build & Developer Experience | One-command local build/test/demo | Makefile/devcontainer/Compose/CI parity |
| C | Continuous Ingestion | Event-driven source ingestion | Git/ADO events indexed incrementally |
| D | Data & Knowledge Quality | Trusted evidence corpus | freshness, provenance, dedupe, quality scoring |
| E | Evaluation | Measurable RAG/agent quality | golden sets + regression gates + adversarial evals |
| F | FinOps | Unit economics and budgets | cost/query, cost/agent, budgets and alerts |
| G | Graph Intelligence | Service/dependency/ownership graph | blast-radius traversal and evidence links |
| H | Human Approval UX | Safe approvals with evidence | approve/reject/rollback UX and audit trail |
| I | Incident Intelligence | Evidence-backed RCA | alert/log/trace/change correlation + ranked hypotheses |
| J | Job/Agent Orchestration | Durable agent workflows | idempotency, retries, state, deadlines, compensation |
| K | Knowledge Lifecycle | Prevent knowledge decay | stale/conflicting docs detected and PRs proposed |
| L | LLM Gateway | Governed model access | routing, quotas, caching, redaction, audit, fallback |
| M | Multi-Agent Coordination | Shared event/state contract | PR/RCA/security/cost/remediation agents cooperate safely |
| N | Network & Identity Security | Private least-privilege runtime | workload identity, private endpoints, egress policy |
| O | Observability & SLOs | Trace every AI/tool decision | OTel + SLOs + model/retrieval/tool dashboards |
| P | Policy-as-Code | Deterministic authorization | OPA policies for retrieval, deploy, model and remediation |
| Q | Quality/Supply Chain | Trusted software artifacts | SBOM, signing, provenance, dependency risk context |
| R | Remediation Library | Reversible runbook catalog | common AKS/cloud failures covered and tested |
| S | Self-Healing Control Plane | Closed-loop recovery | detect->diagnose->plan->authorize->execute->verify |
| T | Threat Model & Red Team | Defend AI-specific attack surface | prompt injection/poisoning/ACL/tool abuse tests |
| U | User/Platform Portal | Productized developer experience | service page, AI evidence, risk, incidents, approvals |
| V | Validation/Digital Twin | Safe pre-production replay | ephemeral simulation and remediation verification |
| W | Workflow/SDLC Intelligence | AI in PR/deploy lifecycle | PR Guardian + change risk + test amplification |
| X | Cross-Cloud Interfaces | Portable control plane | Azure adapter first; AWS/GCP contracts documented |
| Y | Yield/Executive Metrics | Board-visible outcomes | DORA, MTTR, recurrence, hours saved, prevented incidents |
| Z | Zero-Touch Bounded Autonomy | Policy-governed L4 autonomy | certified services self-heal within explicit budgets |

## Delivery and certification rules

The [outcome-gated roadmap](technical-roadmap-24-months.md) defines the only delivery order.
The [System Design](../architecture/design.md) and [Security Threat Model](../governance/security-threat-model.md)
define the autonomy ladder. The [Non-Functional Requirements](../architecture/non-functional-requirements.md),
[Production Readiness](../docs/PRODUCTION-READINESS.md), and [Production Evidence Registry](../docs/PRODUCTION-EVIDENCE.md)
define the required quality, ownership, safety, and evidence gates for a real product capability.
Keeping those rules in their canonical documents prevents this catalogue from drifting into a
second certification checklist.

## Execution order

The A–Z workstreams are themes, not a sequence. Delivery order is owned by the roadmap stages in
[`technical-roadmap-24-months.md`](technical-roadmap-24-months.md):

| Roadmap stage | Workstreams it draws on |
|---|---|
| Stage 0 | A, B, Q, T (architecture/ADRs, build and developer experience, supply chain, threat model and red team) |
| Stage 1 | W, G, E (SDLC intelligence / PR Guardian, graph intelligence, evaluation golden sets) |
| Stage 2 | C, D, L, N, O (continuous ingestion, knowledge quality, LLM gateway, private identity/network, observability) |
| Stage 3 | K, U, F (knowledge lifecycle, portal, FinOps unit economics) |
| Stage 4 | I, M, Y (incident intelligence, shared agent contracts, executive metrics) |
| Stage 5 | J, P, R, S, V, H (orchestration, policy-as-code, remediation library, self-healing control plane, digital twin, approval UX) |
| Stage 6 | Z (zero-touch bounded autonomy) |
| Deferred | X (cross-cloud interfaces) — see the roadmap's explicit deferrals |

Letters are the workstream keys in the table above; where a letter's scope spans stages, the
earlier stage takes only the slice its exit gate needs.
