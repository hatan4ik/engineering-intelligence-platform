# Original Product Capability Reconciliation

This document resets implementation grooming around the **original Engineering Intelligence Platform product architecture**. The P1–P7 corrective sequence repaired structural prerequisites; it is not the product roadmap.

## Product north-star

```text
Engineering + operational sources
        |
        v
Continuous governed ingestion
        |
        v
Engineering knowledge + service/resource graph
        |
        v
Secure AI Gateway / RAG / evidence assembly
        |
        +--> Engineering Q&A / IDE
        +--> PR Guardian / Architecture Guard
        +--> Deployment Failure Investigator
        +--> Incident Intelligence
        +--> Drift Detector
        +--> Knowledge Decay Agent
        +--> Change-risk / predictive intelligence
        |
        v
Durable control plane + deterministic policy + approval
        |
        v
Certified runbooks -> execute -> independent verify
        |
        +--> success -> audit / learn
        `--> failure -> rollback / escalate
```

**Invariant:** the LLM reasons; identity and ACLs constrain evidence; deterministic policy authorizes; allow-listed automation executes; independent signals verify. L5 unrestricted autonomy is unsupported.

## Reconciled capability matrix

Legend: **Implemented** = usable reference implementation on `main`; **Partial** = meaningful primitives exist but product workflow is incomplete; **Skeleton** = contract/example only; **Missing** = not implemented.

| Original product capability | Status after corrective work | Evidence in repo | Next product work |
|---|---|---|---|
| Secure private Azure foundation | Implemented foundation | private Search/OpenAI/Key Vault, AKS Workload Identity, private DNS/endpoints | controlled egress, ingress/API auth, metadata-store private endpoint |
| Continuous code ingestion | Partial/strong | GitHub/ADO events, AST chunks, ACL metadata, ledger/DLQ/replay | webhook auth, real ACL resolver, shared queue, reconciliation/backpressure |
| Organizational memory | Partial | generic work-item/docs/runbook/incident/deployment/conversation model | concrete Boards/Jira/Confluence adapters and governed Teams/Slack decision |
| Hybrid/vector RAG | Partial | Azure Search/OpenAI backend + embedding contracts | real embedding deployment/index vector profile, hybrid query/rerank, quality gates |
| AI Gateway | Partial | FastAPI query path | auth middleware, model routing, budgets, cache, redaction, fallback/audit |
| Service dependency graph | Partial | in-memory graph + manifest extraction | persistent graph; Terraform/Helm/K8s/runtime extraction; SLO/resource/owner links |
| PR Guardian | Partial | deterministic risk + Markdown + durable PR workflow state | real GitHub/ADO PR event adapter, diff/service mapping, check/comment publishing, precision metrics |
| Architecture Guard | Skeleton | risk/policy primitives only | ADR/reference-rule engine + PR evidence/output |
| Deployment Failure Investigator | Partial | deployment-failure analysis + durable workflow | real pipeline webhook/log adapter, last-good diff, output/check/ticket integration |
| Incident Intelligence | Partial/strong | evidence timeline, RCA hypotheses, SLO context, durable workflow | Azure Monitor/App Insights queries, topology correlation, incident-system output |
| Drift Detector | Partial | desired/observed findings + durable workflow | Azure Resource Graph + Terraform plan/state + corrective PR workflow |
| Knowledge Decay Agent | Missing | organizational memory has freshness fields | stale/conflicting knowledge scoring + documentation PR/ticket workflow |
| Predictive change risk | Partial/strong | deterministic risk factors + blast radius + history input | real historical feature store, calibration, deployment gate integration |
| Authoritative state/audit | Implemented local contract | optimistic state + hash-chained audit | production PostgreSQL/Cosmos adapter, retention/immutability/export |
| Durable orchestration | Implemented local contract | leases, retry/backoff, restart recovery, DLQ | Service Bus/PostgreSQL production adapter, compensation/deadlines/concurrency policy |
| Deterministic mutation policy | Partial | Python policy + OPA examples | one authoritative OPA decision contract, bundle version/audit, remove semantic duplication |
| Human approval | Partial | plan-bound expiring approval | Entra approver auth/RBAC + portal/Teams/Slack UX |
| Runbook library / AKS execution | Partial | typed catalog + fixed kubectl adapter + verification/rollback | expand certified failure classes, Azure resource adapters, pre/postconditions/idempotency |
| Digital twin | Skeleton | simulation abstraction | ephemeral namespace/environment replay with independent health signals |
| Self-healing loop | Partial/strong | policy -> execute -> verify -> rollback/escalate | SLO-aware production signals, orchestration integration, action audit and certification |
| OpenTelemetry control-plane telemetry | Skeleton/partial | tracing bootstrap | spans/metrics across retrieval/model/policy/tool/action/workflow and dashboards |
| AI security/red-team | Skeleton | basic injection detector/tool allow-list | adversarial corpus + poisoned index/ACL/confused deputy/egress tests in CI |
| Supply-chain security | Skeleton | provenance contracts | SBOM/signing/attestation/admission workflow |
| FinOps / model economics | Partial | cost attribution and ROI primitives | measured model/search/tool usage, budgets/routing/cache/anomaly alerts |
| Executive control tower | Partial | KPI/ROI models + portal view models | live telemetry/API/dashboard and measured-vs-modeled benefit lineage |
| Cross-cloud | Appropriate abstraction | provider contracts | defer depth until Azure reference implementation is production-deep |
| Bounded L4 autonomy | Correct target, not certified | certification/resilience model | service+environment+runbook evidence, chaos drills, kill-switch and rollback certification |

## Product execution order from here

### Product Track A — Engineering Knowledge that developers can trust
1. Complete hybrid/vector retrieval and evaluation.
2. Complete concrete source adapters and ACL resolution.
3. Persist service/resource/ownership/SLO graph.
4. Add AI Gateway authentication, model routing, budgets, redaction and audit.
5. Deliver authenticated engineering Q&A / IDE-facing API with citations.

### Product Track B — AI-native SDLC
1. Ship real GitHub PR Guardian end-to-end.
2. Add Architecture Guard using ADR/reference architecture rules.
3. Wire change-risk into checks, test amplification and release gates.
4. Ship Deployment Failure Investigator from pipeline event to evidence-backed output.
5. Add Knowledge Decay agent that creates reviewable documentation work, never silently rewrites truth.

### Product Track C — Operational intelligence
1. Connect Azure Monitor/App Insights/OTel evidence sources.
2. Persist and traverse service/resource topology.
3. Ship incident timeline/RCA with evidence citations.
4. Connect Drift Detector to Azure Resource Graph + Terraform/Git desired state.
5. Calibrate historical failure/change similarity and predictive deployment risk.

### Product Track D — Supervised self-healing
1. Make OPA the authoritative mutation decision service.
2. Expand certified runbooks and Azure/AKS action adapters.
3. Connect durable orchestration to remediation workflows.
4. Add ephemeral digital-twin replay for risky plans.
5. Add SLO/error-budget-aware independent verification.
6. Add authenticated approvals and operator control surface.
7. Certify L3 first; L4 only per service/environment/runbook after evidence and chaos drills.

### Product Track E — Enterprise controls and measurable transformation
1. Full control-plane OTel and SLO dashboards.
2. AI red-team CI, supply-chain attestations and admission controls.
3. Live FinOps/model-routing budgets and unit economics.
4. Executive control tower tied to source telemetry.
5. Measure PR cycle time, change failure rate, MTTR, recurrence, prevented incidents, accepted/rejected recommendations and autonomous-action rollback rate.

## Immediate implementation queue

The next code should **not** be another generic platform prerequisite. Execute the product in this order:

1. **PR Guardian E2E** — GitHub PR payload/diff -> changed-service mapping -> graph/risk -> durable workflow/audit -> GitHub Check/comment contract.
2. **Hybrid/vector RAG completion** — embedding adapter + Search vector schema/query + ACL filter + citations + evaluation gate.
3. **Persistent service/resource graph** — repository/IaC/Kubernetes/ownership/SLO projections and blast-radius queries.
4. **Deployment Failure Investigator E2E** — pipeline failure -> logs/deployment/last-good change -> hypotheses -> durable output.
5. **Incident Intelligence E2E** — Azure telemetry adapters -> topology/change correlation -> evidence-backed RCA.
6. **Drift E2E** — Resource Graph/Terraform/Git -> drift finding -> corrective PR recommendation.
7. **Knowledge Decay** — stale/conflicting docs -> evidence -> reviewable documentation PR/ticket.
8. **Self-healing integration** — durable job -> policy -> approval/simulation -> certified adapter -> verify -> rollback/escalate -> audit.

## Acceptance rule

Every new PR must map to one of the original product capabilities above and improve at least one measurable outcome: retrieval quality, developer workflow, change-risk precision, incident diagnosis, remediation safety, security, reliability or unit economics. Corrective P-labels are complete; future PR titles should name the **product capability being delivered**.
