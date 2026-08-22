# Original Architecture Alignment Review

## Executive conclusion

The repository is directionally aligned with the original Engineering Intelligence / self-healing architecture, but it is not yet fully aligned at the implementation level. The strongest alignment is in the control model: authorization-before-retrieval, evidence-backed reasoning, deterministic policy, allow-listed runbooks, verification, rollback and bounded autonomy. The largest gaps are in the private Azure foundation, source coverage, production orchestration, operational integrations and the concrete agent workflows originally promised.

This document is the architectural source of truth for grooming. Future work should close these gaps before expanding scope further.

## Original north-star

```text
Engineering sources / runtime events
        |
        v
Continuous ingestion + provenance + ACLs
        |
        v
Knowledge layer + metadata/service graph
        |
        v
AI Gateway / RAG / model routing
        |
        +--> IDE / engineering Q&A
        +--> PR Guardian
        +--> Deployment Failure Investigator
        +--> Incident Intelligence
        +--> Drift / architecture / knowledge agents
        |
        v
Deterministic policy + approval + runbook catalog
        |
        v
Execute -> verify -> rollback/escalate
        |
        v
Audit + documentation + PR/ticket + learning metrics
```

The LLM is an analysis component, not an identity provider, authorization engine or arbitrary shell executor.

## Alignment matrix

| Original capability | Repository status | Alignment | Required grooming |
|---|---|---:|---|
| Private enterprise AI access | Azure OpenAI adapter exists | Partial | Terraform Azure OpenAI/AI Foundry endpoint, private endpoint/DNS, disable public access, workload identity/RBAC |
| Entra ID + managed identity | `DefaultAzureCredential` and AKS managed identity exist | Partial | Workload Identity/OIDC, explicit role assignments, application auth middleware, group resolution |
| VNet/private endpoints | VNet exists | Weak | Dedicated private-endpoint subnet, private DNS zones, Search/OpenAI/Key Vault/metadata endpoints, egress policy |
| AI Gateway / orchestrator | FastAPI + RAG adapter exist | Partial | Unified gateway contract for auth, model routing, budgets, cache, redaction, audit, fallback |
| Hybrid/vector retrieval | semantic Search adapter + ingestion vector contract | Partial | Real Azure embedding adapter, vector profile/index config, hybrid query, reranking/evaluation |
| Metadata/lineage store | Metadata fields embedded in Search | Weak | Authoritative metadata/event/workflow store such as PostgreSQL/Cosmos; Search is not the system of record |
| Continuous repo ingestion | GitHub/ADO push normalization, AST chunking, ledger/DLQ | Good foundation | Webhook signature validation, shared queue/ledger, Entra/repo ACL resolver, reindex/reconciliation, rate/backpressure |
| Jira/Boards/work items | Architecture docs mention them | Missing implementation | Azure Boards/Jira adapters + ACL/provenance model |
| Confluence/Notion/ADRs/runbooks | ADRs/runbooks represented conceptually | Mostly missing | Document-source adapters, parsing, freshness/owner rules |
| Slack/Teams knowledge | Original design included it | Missing | Treat as optional governed source; retention/privacy policy required before ingestion |
| IDE integration | Original design included VS Code | Missing | Authenticated extension or API contract, citations, repo context |
| PR Guardian | Risk engine + Markdown renderer exist | Partial | Actual GitHub/Azure DevOps workflow/check integration, diff fetch, comment/check output, precision metrics |
| Deployment Failure Investigator | Incident model can correlate deployments | Partial | Pipeline-failure webhook, log collection, last-good diff, rollback recommendation/check output |
| Incident intelligence | Timeline/RCA/SLO primitives exist | Good foundation | Real Azure Monitor/App Insights/OTel queries, topology correlation, historical similarity backend |
| Drift Detection Agent | Original design explicitly included it | Missing | Azure Resource Graph + Terraform/Git reconciliation + corrective PR |
| Architecture consistency agent | Original design included guardrails | Partial | ADR/reference-rule checks, dependency/policy violations, evidence-backed PR output |
| Knowledge decay prevention | Original design included nightly doc PRs | Missing | stale/conflicting-doc detection and generated documentation PR workflow |
| Change-risk scoring | Deterministic service/blast-radius scoring exists | Good foundation | Real service mapping, test coverage/history feeds, calibration and release-gate integration |
| Service dependency graph | In-memory graph + manifest extractor | Partial | Terraform/Helm/K8s/runtime extraction, persistent graph, ownership/SLO/resource links |
| Policy-as-code | OPA examples + Python policy exist | Partial | One authoritative policy decision contract; remove duplicated policy semantics and add policy bundle/version/audit |
| Runbook library | Typed remediation catalog exists | Partial | Concrete AKS/Azure runbooks for target failure classes, idempotency, pre/post conditions, rollback tests |
| Digital twin/safe simulation | simulation abstraction exists | Early | Ephemeral AKS namespace/environment replay and independent verification signals |
| Self-healing loop | execute/verify/rollback primitives exist | Good foundation | Real K8s/cloud action adapters, durable orchestration, SLO-aware verification, audit persistence |
| Human approval UX | signed plan-bound approval primitive exists | Partial | Entra-authenticated approver identity, portal/API/Teams/Slack UX, authorization and expiry/audit |
| Durable multi-agent orchestration | typed state exists | Weak | Persistent workflow engine/store, typed events, resume/retry/compensation, concurrency controls |
| OpenTelemetry | bootstrap exists | Partial | traces for retrieval/model/tool/policy/action, metrics/log correlation, dashboards/SLOs |
| FinOps/model tiering | attribution/ROI primitives exist | Partial | budgets, quotas, model routing, cache, cost anomaly alerts, measured-vs-modeled flags |
| Prompt-injection/red-team | basic detector/tool allow-list exists | Early | adversarial corpus, poisoned-index/ACL/confused-deputy/egress tests integrated into CI |
| Supply-chain security | provenance contract exists | Early | CI SBOM, signing, attestations, admission verification, reachable-risk prioritization |
| Executive control tower | metrics primitives and board narrative exist | Partial | live telemetry sources, dashboard/API, traceable benefit calculations |
| Cross-cloud portability | provider contracts exist | Appropriate future abstraction | Keep Azure as reference implementation; do not let portability block Azure production depth |
| Bounded L4 autonomy | certification/resilience model exists | Correct target | Require service+environment+runbook certification; L5 unrestricted autonomy remains out of scope |

## Critical architecture drift discovered

### 1. Documentation promises a private Azure platform that Terraform does not currently provision
The target architecture names Entra ID, Managed Identity, Private Endpoints, VNet integration, Azure OpenAI, Azure AI Search, metadata storage, Key Vault and observability. The current Terraform only creates a VNet, two subnets, Log Analytics, public-default Azure AI Search and AKS. This is the highest-priority structural gap.

### 2. Search is carrying too much responsibility
Azure AI Search is appropriate for retrieval, but the original design also requires lineage, workflow state, event history, incident/runbook audit and durable orchestration. Those need an authoritative metadata/state store. Retrieval indexes should remain rebuildable projections.

### 3. Source ingestion is much narrower than the original architecture
The original architecture included repositories, Jira/Boards, Confluence/Notion, Slack/Teams, incidents, logs and CI/CD history. The repo currently has strong code-ingestion primitives but almost none of the non-code knowledge adapters.

### 4. The original named agents are not all wired as operational workflows
PR Guardian has logic but no real PR workflow. Deployment Failure Investigator is only partially represented by incident correlation. Drift Detector and Knowledge Decay/Documentation agents are absent.

### 5. Policy semantics are duplicated
OPA policy examples and Python remediation policy coexist without a defined authoritative decision interface. Production architecture should have one policy decision contract/version and treat local Python logic as test/fallback only.

### 6. Observability is not yet an AI control-plane telemetry system
The original design requires cost, latency, retrieval quality, model/tool decisions and action auditability. Current OTel support is bootstrap-level and incident adapters are reference-level.

### 7. Governance autonomy terminology drifted
The program backlog correctly defines L0–L4 and states L5 unrestricted autonomy is out of scope. Any document suggesting a broader Tier 5 must be corrected.

## Priority correction sequence

### P0 — architectural correctness
1. Align all autonomy/security documentation to L0–L4; L5 unsupported.
2. Establish a single target-state architecture and implemented-vs-target matrix.
3. Make OPA/external policy service the authoritative mutation decision boundary.
4. Define Search as projection and introduce an authoritative metadata/workflow/audit store contract.

### P1 — secure Azure foundation
1. Add Azure OpenAI/enterprise model endpoint infrastructure.
2. Add private-endpoint subnet and private DNS.
3. Private endpoints for Search, model endpoint, Key Vault and metadata store.
4. Disable public network access where supported.
5. AKS Workload Identity/OIDC + explicit least-privilege role assignments.
6. Key Vault/secrets integration and controlled egress.
7. API ingress/authentication boundary.

### P2 — complete original SDLC workflows
1. Wire PR Guardian to GitHub and Azure DevOps checks/comments.
2. Add Deployment Failure Investigator pipeline event path.
3. Implement Drift Detector using Azure Resource Graph + Git/IaC.
4. Implement Knowledge Decay/Documentation agent.
5. Add Boards/Jira and document-source ingestion.

### P3 — production self-healing depth
1. Persistent service/resource graph.
2. Real Azure Monitor/OTel topology correlation.
3. Concrete AKS/Azure runbook adapters.
4. Durable workflow state and authenticated approvals.
5. Ephemeral digital-twin replay.
6. SLO-aware verification and rollback.

### P4 — economics, security and scale
1. Model gateway routing/cache/quotas/redaction.
2. Full AI red-team CI suite.
3. SBOM/signing/provenance enforcement.
4. Live FinOps and executive dashboards.
5. Only then deepen AWS/GCP adapters and L4 certification.

## Grooming rule

New features should be accepted only if they either close a gap in this matrix or demonstrably improve safety, reliability, retrieval quality, developer workflow, incident outcomes or unit economics. Avoid adding new milestone labels that do not strengthen the original architecture.
