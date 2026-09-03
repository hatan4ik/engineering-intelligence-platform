# Azure DevOps, AKS & On-Prem Kubernetes Self-Healing Reference Architecture

| | |
|---|---|
| **Classification** | Target proposal — Azure, AKS, and self-healing reference architecture |
| **Owner** | Platform Engineering and SRE |
| **Current implementation state** | [Capability Reconciliation](CAPABILITY-RECONCILIATION.md) |
| **Evidence standard** | [Production Evidence](../docs/PRODUCTION-EVIDENCE.md) |
| **Historical rationale** | [Architecture Alignment Review](ALIGNMENT-REVIEW.md) |

This document describes target state. The implemented reference is intentionally smaller; no
section should be read as a current deployment or autonomy claim.

## 1. Experience and SDLC integration layer

Consumers and triggers:
- Developer/architect chat and API
- VS Code / IDE integration
- GitHub and Azure DevOps PR checks/comments
- Azure DevOps pipeline/deployment events
- Incident/on-call workflows
- Platform portal and human approval UX

Named engineering agents from the original design:
- **PR Guardian** — diff-aware review, internal standards, security/IaC patterns and historical regressions
- **Deployment Failure Investigator** — failed-stage logs, recent changes, last-known-good state and rollback evidence
- **Incident Investigator** — telemetry/change/topology correlation and ranked RCA hypotheses
- **Drift Detector** — deployed Azure/AKS state versus Git/IaC and corrective PRs
- **Architecture Guard** — ADR/reference-architecture and dependency-policy checks
- **Knowledge Decay Agent** — stale/conflicting documentation detection and documentation PRs
- **Remediation Agent** — chooses only registered candidate runbooks; policy decides whether execution is allowed

## 2. Identity, network and trust boundary

Target production controls:
- Entra ID for user/service identity
- AKS OIDC + Workload Identity / managed identities
- private ingress/API gateway boundary
- VNet-isolated runtime
- dedicated private-endpoint subnet
- Private Link/private DNS for Azure AI Search, model endpoint, Key Vault and metadata/state services
- public network access disabled where supported
- explicit least-privilege role assignments
- controlled outbound egress
- secrets in Key Vault; never embedded in prompts/indexes

## 3. Continuous knowledge and event ingestion

Original source classes:
- GitHub / Azure DevOps repositories
- Azure Boards / Jira work items and decisions
- ADRs, runbooks and engineering docs
- Confluence / Notion or equivalent governed document stores
- CI/CD history and deployment metadata
- incident records and postmortems
- Azure Monitor / Log Analytics / App Insights / OpenTelemetry evidence
- optional Slack/Teams knowledge only with explicit retention/privacy governance

Processing requirements:
- AST/logical code chunking plus document-aware parsing
- incremental commit/event processing
- authoritative ACL/provenance/freshness metadata
- secret/PII scanning before indexing
- durable queue/ledger, retries, DLQ and replay
- deletion/rename/reconciliation semantics
- embedding generation and cost telemetry

## 4. Knowledge, retrieval and organizational memory

Separate responsibilities:
- **Azure AI Search / pgvector** — rebuildable retrieval projection: semantic/vector/hybrid search, metadata and ACL filters
- **Authoritative metadata/state store** — lineage, workflow state, approvals, incidents, service ownership, audit references and durable agent state
- **Service/resource graph** — services, APIs, queues, databases, Kubernetes objects, cloud resources, owners, SLOs and dependencies

Search is not the system of record.

## 5. AI Gateway / RAG orchestration

Responsibilities:
- caller authentication and authorization context
- retrieval security trimming **before** model synthesis
- hybrid retrieval + reranking
- provenance/freshness weighting
- citations and confidence/evidence contracts
- prompt-injection isolation/redaction
- model routing by use case/cost/latency
- quotas, budgets, caching and fallback
- model/tool/retrieval OpenTelemetry
- immutable audit correlation IDs

The LLM is never an authorization boundary.

## 6. Engineering intelligence layer

Core intelligence products:
- repo/architecture Q&A with citations
- service/dependency graph and blast-radius analysis
- deterministic/explainable change-risk scoring
- PR review and test amplification
- deployment-failure correlation
- incident timeline/RCA hypotheses
- SLO/error-budget awareness
- historical incident/regression matching
- drift and architecture consistency detection
- knowledge quality/freshness scoring

## 7. Policy and action plane

The execution plane is deliberately deterministic:

`candidate action -> authoritative policy decision -> approval if required -> registered runbook -> execution -> independent verification -> rollback/escalation`

Controls:
- OPA/policy service is the authoritative mutation decision boundary
- service + environment + runbook autonomy certification
- blast-radius/error-budget/time/retry limits
- plan-bound authenticated approvals
- global and per-service kill switches
- deterministic allow-listed runbooks
- independent post-action verification
- rollback/compensation and escalation
- corrective PR/ticket/audit record after action
- K8s-native admission controllers (Gatekeeper/Kyverno) for proactive guardrails
- Node-level self-healing (cordon, drain, terminate) for underlying infrastructure recovery

## 8. Observability and FinOps

Measure both engineering outcomes and AI-platform behavior:
- retrieval precision/grounded-answer rate
- model/retrieval/tool latency
- token/search/embedding/tool cost by service/repo/user/agent
- cache hit ratio and model routing decisions
- PR precision/false positives and cycle time
- change failure rate
- MTTA/MTTR and recurrence
- SLO/error-budget impact
- remediation success, rollback and autonomous-action counts
- prevented incidents and measured engineer-hours saved

## 9. Closed-loop self-healing lifecycle

`Detect -> diagnose -> retrieve evidence -> estimate blast radius -> plan -> simulate when required -> policy -> approve/execute -> verify SLO/state recovery -> rollback or close -> audit -> PR/ticket -> feedback metrics`

The long-term target is **bounded L4 autonomy**, not unrestricted automation.

## 10. Azure reference components

Target stack:
- Entra ID / Managed Identity / Workload Identity
- API gateway/private ingress
- Azure OpenAI / enterprise model gateway
- Azure AI Search and optional PostgreSQL/pgvector
- PostgreSQL/Cosmos-equivalent metadata/workflow/audit state store
- Key Vault
- Azure Container Apps and/or AKS
- Azure Monitor, Log Analytics, Application Insights and OpenTelemetry
- Azure DevOps Repos, Boards and Pipelines
- Azure Resource Graph and Azure Policy
- OPA/policy service
- Redis-compatible cache where justified by workload economics

## Safety invariants

1. Authorization happens before retrieval.
2. Retrieved content is untrusted data, never trusted instruction.
3. The LLM may recommend; deterministic policy authorizes mutation.
4. Model-generated free-form shell is never an autonomous production action.
5. Production mutation resolves to explicit registered runbooks.
6. Every recommendation/action carries evidence and audit correlation.
7. Self-healing begins with reversible, low-blast-radius actions.
8. Verification is mandatory; failed remediation rolls back or escalates.
9. Retry/action budgets prevent automation loops.
10. Kill switch and human override remain available.
11. L4 autonomy is scoped per service + environment + runbook.
12. L5 unrestricted autonomy is unsupported.

## Example AKS & On-Prem Kubernetes Incidents

### Scenario A: HPA Saturation
An HPA configuration change causes CPU saturation and pod instability. The platform correlates the SLO alert with the recent deployment, traverses the service/resource graph, retrieves the HPA diff and prior similar incidents, computes blast radius and proposes the registered rollback runbook. The policy engine checks service autonomy level, error budget and blast-radius limit. If approval is required, the exact plan hash is presented to an authorized operator. The runbook executes, independent telemetry verifies SLO recovery, and the platform creates a corrective PR/incident record with full audit evidence.

### Scenario B: Advanced Node-Level Troubleshooting
A node begins experiencing persistent OOMKilled events and kernel-level network drops (detected via eBPF). The Incident Investigator pulls Kubelet logs, Prometheus host metrics, and eBPF network traces, determining the node is degraded but not yet cordoned. The Remediation Agent proposes a node-drain runbook. Upon approval, the node is cordoned and drained, workloads are successfully rescheduled by the K8s scheduler, and the underlying VM is safely restarted or replaced, successfully recovering the service SLO without human SSH access.
