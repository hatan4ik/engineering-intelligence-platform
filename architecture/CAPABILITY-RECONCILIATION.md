# Original Product Capability Reconciliation

| | |
|---|---|
| **Classification** | Current implementation state — repository/reference evidence, not production certification |
| **Owner** | Platform Engineering |
| **Current design** | [`design.md`](design.md) |
| **Production evidence contract** | [`../docs/PRODUCTION-EVIDENCE.md`](../docs/PRODUCTION-EVIDENCE.md) |

This file is the current-state reconciliation for the **original Engineering Intelligence
Platform product architecture**. It records what is present in the repository; it must not be
read as a claim that the capability is deployed, production-proven, or approved for a broader
autonomy tier.

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
Authenticated AI Gateway / RAG / evidence assembly
        |
        +--> Engineering Q&A / IDE
        +--> PR Guardian / Architecture Guard
        +--> Deployment Failure Investigator
        +--> Incident Intelligence
        +--> Drift Detector
        +--> Knowledge Decay Agent
        +--> Predictive change risk
        |
        v
Durable control plane + plan-bound approval + OPA policy
        |
        v
Ephemeral digital twin -> certified runbook -> independent verify
        |
        +--> success -> immutable audit / telemetry / learn
        `--> failure -> rollback / escalate
```

**Invariant:** models reason and recommend; authenticated identity and ACLs constrain evidence; OPA authorizes production mutations; allow-listed adapters execute; independent signals verify. L5 unrestricted autonomy remains unsupported.

## Product focus

The architecture above is the target portfolio, not a claim that each vertical is an active
product. The defined initial product is **PR Guardian** for one or two future named repositories,
starting in shadow mode; no pilot repository is currently named or enabled.
Architecture Guard, deployment investigation, incident intelligence, drift, and remediation are
reference workflows until they consume the shared product finding, evidence, outcome, and
evaluation contracts described in the [product maturity roadmap](../roadmap/technical-roadmap-24-months.md).
They do not share PR Guardian's pilot or promotion authority.

## Current capability matrix

Legend: **Implemented reference** = executable, CI-covered repository path exists.
**Partial** = a useful implementation exists but external integration, operational breadth, or
quality evidence is incomplete. **Adapter present** = a production-facing interface exists but is
not itself proof that the dependency is provisioned, wired, or operated. **Not certified** =
implementation may exist, but no service/environment/runbook production evidence is recorded.

| Original capability | Current status | Implemented evidence | Remaining depth |
|---|---|---|---|
| Secure private Azure foundation | Implemented reference foundation | private Search/OpenAI/Key Vault, AKS Workload Identity, private endpoints/DNS | production ingress/egress, hardened AKS/workload posture, DR, and environment proof |
| Continuous code ingestion | Strong reference | GitHub/ADO events, AST chunks, ACL metadata, ledger/DLQ/replay, source catalog lifecycle, ACL reconciliation, deletion, and missing-index repair | managed provider scheduling, shared queue/backpressure, broader source adapters, and retained source-SLA evidence |
| Organizational memory | Partial | governed work-item/docs/runbook/incident/deployment/conversation model | concrete Jira/Confluence/Teams/Slack adapters |
| Hybrid/vector RAG | Reference-partial | Azure Search hybrid/vector retrieval, ACL filter, suspicious-evidence quarantine, and evaluation | deterministic Guardrail SLM/equivalent, production index tuning, adversarial expansion, and quality calibration |
| AI Gateway | Reference-partial | Entra bearer auth, trusted groups/roles, redaction, model routing, and request-budget contract | per-principal rate/concurrency enforcement, Graph group-overage resolver, operator UX, and production proof |
| Service/resource graph | Implemented reference | persistent graph, service/resource/owner/SLO projections, blast radius | broader runtime/IaC extractors and scale tuning |
| PR Guardian | Shadow E2E reference | GitHub event -> diff/service mapping -> graph/risk -> workflow -> neutral check/comment; local durable finding/outcome store; explicit reviewer-label closure record, canonical feedback-export/report digests, and non-authorizing pilot/promotion validators | named pilot configuration, externally retained evidence, live reviewer outcomes, authorized retrieval citations, independent post-merge correlation, and repository-specific calibration |
| Architecture Guard | Implemented reference | ADR/reference architecture rules with deterministic findings | broader rule catalog and PR publishing integration |
| Deployment Failure Investigator | Implemented E2E | pipeline failure normalization, evidence/last-good correlation, hypotheses, durable output | additional pipeline providers and ticket UX |
| Incident Intelligence | Implemented E2E | Azure Monitor evidence adapter, topology/change correlation, evidence-backed RCA | richer App Insights/OTel queries and incident-system publishing |
| Drift Detector | Implemented E2E | Git/Terraform desired state + Azure Resource Graph observed state -> durable drift finding | corrective PR automation and more resource projections |
| Knowledge Decay Agent | Implemented reference | stale/ownerless/conflicting knowledge scoring; tenant-scoped deterministic maintenance planning; explicit human disposition and independent source-revision correlation contract | approved source-specific publisher and system of record, real reviewer/source outcomes, and freshness SLO evidence |
| Predictive change risk | Implemented reference | historical calibration, explicit confidence/evidence, deployment-risk output | real feature-store history and threshold calibration |
| Authoritative state | Reference boundary | SQLite lifecycle contract and Cosmos DB adapter with `_etag` CAS, app versions, atomic transition receipts, idempotency, cancellation, and restart coverage | provision/wire managed state, multi-region policy, backup/restore, retention, and production proof |
| Audit | Reference boundary | hash-chained local audit, control-plane action audit, and lifecycle bridge that fails a transition when audit export fails | immutable external export/retention policy and retained operational evidence |
| Durable orchestration | Reference boundary plus non-consequential Temporal evidence worker | SQLite reference semantics; fail-closed Temporal configuration/server wrapper/private PostgreSQL declarations; mTLS worker chart, `eip.control-plane-evidence.v1`, and unregistered `eip.persist-workflow-lifecycle.v1` activity | register product workflows only after they consume canonical lifecycle contracts; schema migration, recovery/restore drills, immutable audit export, and production evidence |
| Mutation policy | Implemented | authoritative OPA contract, fail-closed client, OPA-native CI tests | bundle distribution/version promotion operations |
| Human approval | Implemented L3 primitive | exact plan-hash HMAC approval with expiry + Entra identity boundary | portal/Teams/Slack approval UX and approver-role mapping |
| Runbook library / AKS execution | Implemented reference | fixed typed runbooks, argv-only Kubernetes adapter, verify/rollback/escalation | more certified failure classes and Azure-resource actions |
| Digital twin | Implemented reference | ephemeral `eip-sim-*` Kubernetes sandbox, identity stripping, same adapter/verification, guaranteed cleanup | richer dependency replay/data fixtures and retained environment evidence |
| Self-healing loop | Implemented supervised reference | incident evidence -> plan -> durable approval -> OPA -> twin -> execute -> verify -> rollback/escalate -> audit | production runbook breadth, managed durable dependencies, and live operational drills |
| OpenTelemetry control-plane telemetry | Reference-partial | HTTP correlation/W3C trace context, temporal evidence carrier, and telemetry-event primitives | full cross-process instrumentation, collector/dashboard packaging, alert thresholds, and production SLO history |
| AI security/red-team | Implemented CI gate | poisoned evidence, policy bypass, secret exfiltration, ACL isolation, confused-deputy corpus | larger adversarial corpus and network-egress exercises |
| Supply-chain security | Implemented reference gate | exact dependency pins, red-team gate, and a CycloneDX SBOM generated from the built CI image | registry-backed image signing/keyless attestation and cluster admission integration |
| FinOps / model economics | Partial/strong | token/search/tool usage events, cost rates, gateway budgets, OTel cost metrics | anomaly alerts and measured routing optimization |
| Executive control tower | Partial | KPI/ROI models plus live telemetry primitives | dashboard/API packaging and measured benefit lineage |
| Cross-cloud | Appropriate abstraction | provider contracts maintained | intentionally deferred until Azure depth is complete |
| L3 supervised autonomy | Not certified; implementation path exists | plan-bound approval, OPA, digital twin, rollback, kill-switch/error-mode primitives, evidence-bound certification report | execute and retain real service/environment/runbook drills |
| L4 bounded autonomy | Not certified | per-service/environment/runbook certification model and exercise evidence digest | real chaos evidence for every required control before promotion |

## What remains before production L3/L4 promotion

1. Execute real, retained exercises per service/environment/runbook for successful remediation, verification failure, rollback, kill switch, policy outage, audit outage and error-budget exhaustion.
2. Add broader certified runbooks for common Kubernetes/Azure failure classes with explicit preconditions, postconditions and rollback semantics.
3. Add immutable audit export plus production durable queue backend.
4. Package operational dashboards/alerts around the new control-plane metrics and SLO projection.
5. Integrate signed image attestations with cluster admission policy.
6. Calibrate predictive-risk and PR-Guardian thresholds against real deployment history.

## Evidence discipline

Every status above is repository evidence only unless linked to a retained, scoped production
record. Before moving a real-data pilot, PR Guardian control, L3 pilot, or L4 capability forward,
record the evidence specified in [`../docs/PRODUCTION-EVIDENCE.md`](../docs/PRODUCTION-EVIDENCE.md).
Evidence expires when the relevant environment, identity, model/prompt, policy, runbook, or data
classification materially changes.

## Promotion rule

No service moves to L3 or L4 because the implementation exists. Promotion is **service + environment + runbook specific** and requires a complete evidence set with no failed exercise, no missing evidence reference, no observed blast radius above the certified bound, independent verification, and security review. L4 additionally requires error-budget enforcement evidence and all bounded-autonomy controls.

## Acceptance rule

Every future PR must map to an original product capability and improve at least one measurable outcome: retrieval quality, developer workflow, change-risk precision, incident diagnosis, remediation safety, security, reliability or unit economics.
