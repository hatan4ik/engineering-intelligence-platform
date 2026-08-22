# Engineering Intelligence Platform — System Design

| | |
|---|---|
| **Status** | Living document — reviewed against `main` |
| **Owners** | Platform Engineering |
| **Execution source of truth** | [`CAPABILITY-RECONCILIATION.md`](CAPABILITY-RECONCILIATION.md) |
| **Threat model** | [`../governance/security-threat-model.md`](../governance/security-threat-model.md) |

## Contents

- [1. Context and scope](#1-context-and-scope)
- [2. Goals and non-goals](#2-goals-and-non-goals)
- [3. System overview](#3-system-overview)
- [4. Design invariants](#4-design-invariants)
- [5. Detailed design](#5-detailed-design)
  - [5.1 Knowledge plane](#51-knowledge-plane)
  - [5.2 Retrieval and AI gateway](#52-retrieval-and-ai-gateway)
  - [5.3 Intelligence plane](#53-intelligence-plane)
  - [5.4 Control plane](#54-control-plane)
  - [5.5 Execution plane](#55-execution-plane)
- [6. Security model](#6-security-model)
- [7. Data model](#7-data-model)
- [8. Failure modes](#8-failure-modes)
- [9. Observability and FinOps](#9-observability-and-finops)
- [10. Testing strategy](#10-testing-strategy)
- [11. Alternatives considered](#11-alternatives-considered)
- [12. Risks and open questions](#12-risks-and-open-questions)

---

## 1. Context and scope

Engineering organizations pay a structural scaling tax: fragmented knowledge, senior-engineer
bottlenecks, repeat incidents, and architecture drift grow faster than headcount. This platform
turns repositories, work items, ADRs, runbooks, CI/CD history, and operational telemetry into a
**governed intelligence layer embedded in the SDLC** — and, once its recommendations are proven
trustworthy, into **supervised self-healing** for certified failure classes.

This document describes the system as designed and the contracts implemented on `main`.
It does not restate delivery status; the
[capability reconciliation](CAPABILITY-RECONCILIATION.md) grades every capability as
Implemented / Partial / Skeleton / Missing and owns the execution queue.

**In scope:** knowledge ingestion, secure retrieval, SDLC and operational intelligence agents,
the durable control plane, and bounded remediation execution on Azure/AKS.

**Out of scope:** training or hosting foundation models, unrestricted (L5) autonomy, and
replacing human accountability for high-blast-radius production changes.

## 2. Goals and non-goals

### Goals

1. **Grounded answers, never ungrounded ones** — every answer and recommendation carries
   citations to authorized evidence; empty authorized retrieval returns an explicit
   insufficient-evidence result rather than a guess.
2. **Authorization before retrieval** — identity and ACLs constrain the evidence set *before*
   any content reaches a model; security trimming is a property of the search layer, not a
   post-filter on model output.
3. **Deterministic authority** — an LLM may reason, correlate, and propose; only deterministic
   policy authorizes mutation, only allow-listed runbooks execute it, and independent signals
   verify it.
4. **Evidence-gated autonomy** — autonomy is earned per service, environment, and runbook
   through certification exercises (L0 → L4), never granted to an agent wholesale.
5. **Everything auditable** — every decision carries a correlation ID, a plan hash, and an
   append-only, hash-chained audit trail.

### Non-goals

- L5 unrestricted autonomy ("AI has cluster-admin") — explicitly unsupported.
- Building or fine-tuning foundation models — inference is routed to enterprise model APIs
  (Azure OpenAI) under tenant isolation and zero-retention terms.
- Real-time chat UX — the product surfaces are engineering workflows (PRs, incidents,
  deployments), not a general-purpose chatbot.

## 3. System overview

```mermaid
flowchart TD
    subgraph SOURCES["Engineering and operational sources"]
        GIT["Git / GitHub / Azure DevOps"]
        WORK["Work items / ADRs / wiki / runbooks"]
        OPS["AKS / Azure Monitor / logs / traces / deployments"]
    end

    subgraph KNOWLEDGE["Knowledge plane — ingestion/"]
        ING["Governed ingestion<br/>events → chunk → ACL → index<br/>ledger / DLQ / replay"]
        IDX[("Search index<br/>+ metadata")]
        GRAPH["Service / dependency /<br/>ownership graph"]
    end

    subgraph GATEWAY["AI gateway — app/"]
        RAG["Identity → ACL filter → retrieve<br/>→ enterprise LLM → citations"]
    end

    subgraph AGENTS["Intelligence plane — intelligence/, product/"]
        PRG["PR Guardian"]
        DFI["Deployment Failure Investigator"]
        INC["Incident Investigator"]
        DRIFT["Drift Detector"]
        RISK["Change-risk engine"]
    end

    subgraph CONTROL["Control plane — control_plane/, orchestration/, state/"]
        WF["Durable workflows + plan hashes"]
        POL["Deterministic policy"]
        APPR["Plan-bound human approvals"]
        AUDIT[("Hash-chained audit log")]
    end

    subgraph EXEC["Execution plane — remediation/"]
        RB["Certified runbook catalog"]
        K8S["Kubernetes / Azure adapters"]
        VER["Independent verification"]
    end

    SOURCES --> ING --> IDX
    ING --> GRAPH
    IDX --> RAG
    GRAPH --> AGENTS
    RAG --> AGENTS
    AGENTS --> WF
    WF --> POL --> APPR
    APPR --> RB --> K8S --> VER
    VER -->|healthy| AUDIT
    VER -->|unhealthy| ROLLBACK["Rollback / escalate"] --> AUDIT
    K8S -.->|telemetry feeds back| SOURCES
    WF --> AUDIT
```

The loop closes: execution telemetry re-enters the knowledge plane, so every incident,
deployment, and remediation becomes evidence for the next decision.

## 4. Design invariants

These hold at every layer and every autonomy level. A change that violates one is a
design regression, not a trade-off.

| # | Invariant | Enforced by |
|---|---|---|
| I1 | Authorization happens **before** retrieval | ACL filter compiled into the search query (`ingestion/azure_search.py`, `app/rag/azure_backend.py`) |
| I2 | The LLM recommends; **deterministic policy** authorizes mutation | `remediation/policy.py` `authorize()`; risk thresholds in `intelligence/pr_guardian.py` |
| I3 | Production mutation is restricted to **allow-listed, reversible runbooks** | Typed catalog in `remediation/catalog.py` |
| I4 | Every answer/action carries **evidence and an audit trail** | Plan hashes + `state/audit.py` hash chain |
| I5 | **Verification is mandatory**; failed remediation escalates, never loops | `remediation/executor.py`; control-loop `VERIFY → ESCALATE` path |
| I6 | Retrieved content is **data, never instructions** | Injection detection (`security/adversarial.py`); post-generation allow-list checks |
| I7 | **Kill switch and human override** exist at every autonomy level | Autonomy policy (`resilience/policy.py`), approval gates |
| I8 | Autonomy is **earned per service/environment/runbook** with exercised evidence | L4 certification (`resilience/exercises.py`) |

## 5. Detailed design

### 5.1 Knowledge plane

Incremental, event-driven ingestion. A changed file is replaced independently; a deletion
removes exactly that document's chunks; full reindex is reserved for schema migrations.

```mermaid
flowchart LR
    EV["GitHub / ADO<br/>push event"] --> NORM["Normalize<br/>ingestion/events.py"]
    NORM --> LEDGER{"Seen before?<br/>ledger.py"}
    LEDGER -->|duplicate| SKIP["Acknowledge,<br/>no work"]
    LEDGER -->|new| LOAD["Load changed files<br/>providers.py"]
    LOAD --> CHUNK["Chunk<br/>Python → AST symbols<br/>other → bounded text"]
    CHUNK --> ACL["Attach ACL + provenance<br/>acl.py"]
    ACL --> EMB["Embedding contract<br/>embeddings.py"]
    EMB --> WRITE["Replace document chunks<br/>index.py / azure_search.py"]
    WRITE --> DONE["Ledger: completed"]
    LOAD -->|failure| DLQ[("DLQ")]
    CHUNK -->|failure| DLQ
    WRITE -->|failure| DLQ
    DLQ --> REPLAY["replay.py<br/>operator-driven"] --> LOAD
```

Key decisions:

- **Chunk identity** includes source, commit, ordinal/symbol, and a content hash; **document
  identity** excludes the commit, so a new version of a file replaces its stale chunks.
- **Idempotency is durable** (SQLite ledger locally; the same interface targets
  Cosmos DB/PostgreSQL in production). A crashed worker re-processes; a completed event is
  skipped; a poisoned event lands in the DLQ with its error, and replay is explicit.
- **ACLs are data**: each chunk carries `acl_groups`/`acl_users` resolved at ingestion time.
  Organizational memory (work items, docs, incidents, conversations) shares the same
  normalized model (`knowledge_normalizers.py`), so one trimming mechanism covers all sources.

### 5.2 Retrieval and AI gateway

```mermaid
sequenceDiagram
    autonumber
    participant C as Caller
    participant API as FastAPI /v1/query
    participant S as Azure AI Search
    participant LLM as Azure OpenAI

    C->>API: question + identity (groups)
    API->>API: resolve authorized groups,<br/>correlation ID
    API->>S: query with ACL filter<br/>compiled into the request
    S-->>API: authorized chunks only
    alt no authorized evidence
        API-->>C: explicit insufficient-evidence answer
    else evidence found
        API->>LLM: question + delimited evidence<br/>(system prompt: evidence is data)
        LLM-->>API: grounded answer
        API-->>C: answer + citations + correlation ID
    end
```

The critical property is step 3: the ACL filter is part of the search request itself, so
content the caller is not entitled to **never enters the candidate set** — there is no code
path in which the model sees unauthorized text and the platform must "remember" to redact it.

Runtime modes: `EIP_BACKEND=deterministic` (local/CI, no cloud dependency) and
`EIP_BACKEND=azure` (Azure AI Search + Azure OpenAI via `DefaultAzureCredential`).

### 5.3 Intelligence plane

Agents share three inputs — the knowledge index, the service graph, and history — and one
output contract: an evidence-carrying analysis handed to the control plane. **No agent
mutates anything.**

The service graph (`intelligence/graph.py`) is extracted from manifests and answers two
questions deterministically: *who depends on this service* (reverse-dependency traversal,
cycle-safe) and *what is the highest criticality tier in the blast radius*.

Change risk (`intelligence/risk.py`) is a deterministic, explainable score: each factor
(critical-service blast radius, diff size, IaC touch, security-boundary touch, weak test
evidence, historical regressions) contributes points and a human-readable evidence line.
The full E2E path for the flagship agent:

```mermaid
sequenceDiagram
    autonumber
    participant GH as GitHub
    participant API as /v1/events/github
    participant G as PRGuardianService
    participant CP as Control plane
    participant CHK as GitHub Checks

    GH->>API: pull_request webhook
    API->>API: verify X-Hub-Signature-256<br/>(fail closed)
    API->>G: normalized PR event
    G->>GH: fetch changed files (diff API)
    G->>G: paths → services → blast radius<br/>→ deterministic risk score
    G->>CP: start_pr_review:<br/>durable workflow + plan hash<br/>+ audit event
    G->>CHK: check run:<br/>success / neutral / action_required<br/>+ evidence markdown
    CHK-->>GH: visible on the PR
```

Score thresholds map to controls: `≥55` extended tests, `≥70` additional approval,
`≥90` merge block. The repository runs this agent on itself
(`.github/workflows/pr-guardian.yml`).

Incident intelligence (`intelligence/incidents.py`) reconstructs an ordered evidence
timeline (alerts, metrics, logs, K8s events, deployments, prior incidents), correlates
deployments with failure onset, and emits **hypotheses that cite evidence IDs** —
facts and inference are structurally separated. Deployment-failure investigation and
drift detection follow the same pattern with their own evidence types.

### 5.4 Control plane

Every consequential decision becomes a **workflow record** with optimistic concurrency and a
**plan hash** — the SHA-256 of the exact analysis/decision it was created from.

```mermaid
stateDiagram-v2
    [*] --> RECEIVED
    RECEIVED --> DIAGNOSING
    DIAGNOSING --> PLANNED
    PLANNED --> WAITING_APPROVAL: policy requires human
    PLANNED --> EXECUTING: policy allows automation
    WAITING_APPROVAL --> EXECUTING: valid plan-bound approval
    WAITING_APPROVAL --> ESCALATED: rejected / expired
    EXECUTING --> VERIFYING
    VERIFYING --> SUCCEEDED: independent signals healthy
    VERIFYING --> ROLLED_BACK: unhealthy → compensate
    ROLLED_BACK --> ESCALATED
    VERIFYING --> ESCALATED: rollback failed
    EXECUTING --> FAILED: unrecoverable error
    SUCCEEDED --> [*]
    ESCALATED --> [*]
    FAILED --> [*]
```

**Approvals are plan-bound and expiring** (`orchestration/approvals.py`): an approval is an
HMAC signature over `workflow_id | approver | plan_hash | issued_at`. If the plan changes,
the hash changes and every prior approval is invalid — an operator can never approve a plan
they have not seen. Stale approvals (default 15 minutes) and clock-skewed timestamps are
rejected.

**Durable execution** (`orchestration/jobs.py`, `runner.py`): a SQLite-backed job queue with
lease-based claiming, exponential-backoff retry, and a dead-letter state after
`max_attempts`. A worker crash mid-job is recovered by lease expiry — the job is reclaimed,
never lost. The same contract targets Service Bus/PostgreSQL in production.

**Audit** (`state/audit.py`): append-only events where each record carries the hash of its
predecessor. `verify_chain()` detects any insertion, deletion, or mutation. Every event
carries correlation ID, actor, action, resource, and payload.

### 5.5 Execution plane

```mermaid
flowchart LR
    PLAN["Proposed action<br/>(agent output)"] --> CAT{"In certified<br/>runbook catalog?"}
    CAT -->|no| ESC1["Escalate to human"]
    CAT -->|yes| POL{"Deterministic policy<br/>authorize()"}
    POL -->|deny| ESC1
    POL -->|allow + approval required| HUM{"Plan-bound<br/>approval?"}
    POL -->|allow| SIM
    HUM -->|no / expired| ESC1
    HUM -->|yes| SIM["Simulation / digital-twin gate"]
    SIM --> EXECUTE["Fixed-command adapter<br/>kubernetes_adapter.py"]
    EXECUTE --> VERIFY{"Independent<br/>verification"}
    VERIFY -->|healthy| CLOSE["Audit + close"]
    VERIFY -->|unhealthy| RB["Rollback"]
    RB -->|rolled back| ESC2["Escalate + audit"]
    RB -->|rollback failed| ESC2
```

- The runbook catalog is **typed and closed**: an action is a fixed command template with
  declared reversibility, blast radius, and risk tier — agents select from the catalog,
  they cannot compose arbitrary commands.
- The Kubernetes adapter executes **fixed argument vectors** (no shell, no string
  interpolation of model output).
- Verification uses signals independent of the action path where practical (SLO/error-budget
  state, not the exit code of the mutation itself).
- The legacy demo loop (`app/agents/control_loop.py`) preserves the same phase machine
  (`DETECT → DIAGNOSE → PLAN → POLICY → APPROVE → EXECUTE → VERIFY → COMPLETE/ESCALATE`)
  for the AKS scenario runner.

## 6. Security model

Trust boundaries, from least to most trusted:

```mermaid
flowchart TD
    subgraph UNTRUSTED["Untrusted input"]
        WEB["Webhooks"]
        DOCS["Retrieved content<br/>(code, tickets, docs)"]
        MODEL["Model output"]
    end
    subgraph GOVERNED["Governed evidence"]
        IDX2[("ACL-trimmed index")]
    end
    subgraph AUTHORITY["Deterministic authority"]
        POLICY["Policy + catalog + approvals"]
    end
    subgraph BLAST["Mutation surface"]
        CLUSTER["AKS / Azure resources"]
    end

    WEB -->|HMAC signature verification| GOVERNED
    DOCS -->|ACL filter + injection detection| IDX2
    IDX2 -->|delimited as data| MODEL
    MODEL -->|"proposals only — validated against catalog"| AUTHORITY
    AUTHORITY -->|allow-listed fixed commands| CLUSTER
```

Threat-to-control mapping (full model in
[`security-threat-model.md`](../governance/security-threat-model.md)):

| Threat | Control |
|---|---|
| Prompt injection via retrieved content | Evidence delimited as data (I6); injection scoring in `security/adversarial.py`; proposals validated against the closed catalog **after** generation |
| Cross-team data exfiltration | ACL filter compiled into every search request (I1) |
| Forged webhooks | Fail-closed HMAC `X-Hub-Signature-256` verification |
| Approval replay / confused deputy | Plan-hash-bound, expiring HMAC approvals |
| Hallucinated remediation | Closed runbook catalog; deterministic policy; mandatory independent verification |
| Automation loops repeating harm | Bounded retries, DLQ, escalation instead of retry-forever (I5) |
| Audit tampering | Hash-chained append-only log with chain verification |
| Model/token abuse | Per-operation cost telemetry (`telemetry/events.py`); budgets are tracked FinOps work |

### Autonomy ladder

| Level | May do | Gate to enter |
|---|---|---|
| L0 | Observe, summarize | Observability + audit |
| L1 | Recommend with evidence | Citation coverage + confidence |
| L2 | Create PRs / tickets / runbook proposals | Exact proposed action + rollback path |
| L3 | Execute low-risk **non-production** remediation | Policy + allow-listed runbook + verification |
| L4 | Execute allow-listed reversible **production** remediation | All L3 controls **+ per service/environment/runbook certification with exercised evidence** (`resilience/exercises.py`) |
| L5 | — | Unsupported by design |

## 7. Data model

| Record | Module | Key properties |
|---|---|---|
| `Chunk` | `ingestion/models.py` | Content-hash ID; document ID excludes commit; carries ACL, provenance, symbol, ordinal |
| `ServiceRecord` | `state/models.py` | Owner, tier, dependencies, SLO target, autonomy level; versioned |
| `WorkflowRecord` | `state/models.py` | Kind, status, correlation ID, plan hash; optimistic concurrency (`VersionConflict`) |
| `AuditEvent` | `state/models.py` | Actor, action, resource, payload, `previous_hash` → `event_hash` chain |
| `Approval` | `orchestration/approvals.py` | HMAC over workflow + approver + plan hash + timestamp |
| `Job` | `orchestration/jobs.py` | Lease, attempts/max-attempts, backoff, DLQ status |
| `OperationEvent` | `telemetry/events.py` | Correlation ID, latency, tokens, model/search/tool cost, per repo/service/agent/user |

System-of-record rule: **Azure AI Search is never the system of record** for services,
workflows, approvals, or audit — those live in the authoritative state store; the index is
a rebuildable projection.

## 8. Failure modes

| Failure | Behavior | Recovery |
|---|---|---|
| Search index unavailable during ingestion | Event fails → ledger marks failed → DLQ with error | `replay.py` after dependency recovers; idempotent by event ID |
| Search unavailable at query time | Explicit error; never silent fallback to ungrounded answers | Retry; deterministic mode for local/CI |
| Empty authorized retrieval | Explicit insufficient-evidence answer (by design, not a failure) | — |
| Worker crash holding a job lease | Lease expires → job reclaimed by next worker | Automatic; attempts counted toward DLQ bound |
| Poisoned event crash-looping | Bounded attempts → dead-letter, never infinite retry | Operator replay after fix |
| Plan changed after approval issued | Plan hash mismatch → approval invalid → `PermissionError` | Re-approve the new plan |
| Remediation verification fails | Rollback, then escalate; never re-execute in a loop | Human on-call owns escalation |
| Audit chain verification fails | Treated as integrity incident | Investigate; the chain localizes the first divergent record |
| Forged/replayed webhook | 401 before any parsing of the payload body | — |

## 9. Observability and FinOps

- **Tracing**: OpenTelemetry spans (`app/observability.py`) around query and PR-guardian
  paths, keyed by correlation ID; exporter configured via `OTEL_EXPORTER_OTLP_ENDPOINT`.
- **Operation telemetry**: every agent operation emits an `OperationEvent` with latency,
  token counts, and model/search/tool cost — the unit-economics feed for cost per query /
  team / agent (`finops/attribution.py`) and outcome ROI (`finops/outcomes.py`).
- **Audit ≠ telemetry**: audit is the tamper-evident record of decisions; telemetry is the
  operational/cost signal. They share correlation IDs so any decision can be joined to its
  cost and latency.

## 10. Testing strategy

| Layer | Approach | Examples |
|---|---|---|
| Contracts | Pure-unit over dataclass contracts, no I/O | risk scoring, chunk identity, approval HMAC |
| Durability | Real SQLite in `tmp_path`; crash/redelivery simulated | ledger DLQ, job lease expiry, audit chain |
| Composition | Fake providers, real control plane | PR Guardian E2E, incident workflow |
| API | FastAPI `TestClient` against the real app | webhook signature, ACL headers, error paths |
| Policy | Deterministic scenario tables | autonomy gates, L4 certification evidence |
| Infra | `terraform fmt/validate`, `helm lint`, container build in CI | — |

CI gates every PR (`ci.yml`); the PR Guardian workflow additionally reviews every PR's own
diff and posts its evidence — the platform dogfoods itself.

## 11. Alternatives considered

| Decision | Chosen | Rejected | Why |
|---|---|---|---|
| Model hosting | Enterprise API (Azure OpenAI) under tenant isolation | Self-hosted open-weights on bare metal | Zero-retention enterprise terms give the IP guarantee without the GPU estate and MLOps burden; the RAG plane, not the model, is the differentiator |
| Retrieval store | Azure AI Search (semantic + planned vector profile) | pgvector | Managed security trimming, semantic ranking, and Entra integration outweigh portability; the `Index` protocol keeps pgvector possible |
| Risk authority | Deterministic, explainable scoring | LLM-judged risk | A merge gate must be reproducible, auditable, and immune to prompt injection; the LLM contributes evidence, not the verdict |
| Mutation policy | Typed in-code policy converging on OPA as the single decision service | Prose runbooks + human judgment only | Policy-as-code is testable and versioned; OPA convergence is tracked work — the current Python/OPA duplication is a known defect, not a design choice |
| Local durability | SQLite implementations of production contracts | Mocks, or cloud services required for tests | Real concurrency/durability semantics in CI; production adapters (PostgreSQL/Cosmos, Service Bus) implement the same interfaces |
| Autonomy | Bounded L4 ceiling, per-runbook certification | L5 general autonomy | Blast radius of a wrong mutation is unbounded; evidence-gated autonomy is the product's core trust claim |

## 12. Risks and open questions

Tracked honestly; grades and queue live in the
[capability reconciliation](CAPABILITY-RECONCILIATION.md).

1. **API identity is not yet Entra-backed** — group headers are a development affordance;
   production requires token-validated identity before the gateway can be exposed.
2. **Policy duplication** — Python policy and OPA examples coexist; until OPA is the single
   decision service, drift between them is possible.
3. **Vector retrieval is contract-only** — semantic reranking works today; embedding
   deployment and hybrid query are queued, and recall claims should not be made before the
   evaluation harness gates them.
4. **Verification independence** — some verification signals still derive from the action
   path; SLO-based independent verification is required before L4 certification is credible.
5. **Local contracts vs production adapters** — SQLite semantics are proven; the
   PostgreSQL/Cosmos/Service Bus adapters are not yet written, and subtle semantic drift
   (isolation, lease clocks) is a real risk when they are.
