# Original Product Capability Reconciliation

This file is the current-state reconciliation for the **original Engineering Intelligence Platform product architecture**. It replaces the earlier corrective/P-track view with what is actually present on `main` after the product-completion sequence through production identity/state and certification evidence.

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

## Current capability matrix

Legend: **Implemented** = executable reference/product path exists and is CI-covered. **Partial** = useful production-capable path exists but operational breadth or external integration remains. **Not certified** = implementation exists but production evidence is intentionally still required.

| Original capability | Current status | Implemented evidence | Remaining depth |
|---|---|---|---|
| Secure private Azure foundation | Implemented foundation | private Search/OpenAI/Key Vault, AKS Workload Identity, private endpoints/DNS | controlled egress and deployment-specific ingress hardening |
| Continuous code ingestion | Partial/strong | GitHub/ADO events, AST chunks, ACL metadata, ledger/DLQ/replay | shared queue/backpressure and broader source reconciliation |
| Organizational memory | Partial | governed work-item/docs/runbook/incident/deployment/conversation model | concrete Jira/Confluence/Teams/Slack adapters |
| Hybrid/vector RAG | Implemented reference | Azure Search hybrid/vector retrieval, ACL filter, safe evidence synthesis, evaluation | production index tuning and quality calibration |
| AI Gateway | Implemented production boundary | Entra bearer auth, trusted groups/roles, redaction, model routing, request budgets | Graph group-overage resolver and operator UX |
| Service/resource graph | Implemented reference | persistent graph, service/resource/owner/SLO projections, blast radius | broader runtime/IaC extractors and scale tuning |
| PR Guardian | Implemented E2E | GitHub event -> diff/service mapping -> graph/risk -> durable workflow -> check/comment contract | precision measurement on real org history |
| Architecture Guard | Implemented reference | ADR/reference architecture rules with deterministic findings | broader rule catalog and PR publishing integration |
| Deployment Failure Investigator | Implemented E2E | pipeline failure normalization, evidence/last-good correlation, hypotheses, durable output | additional pipeline providers and ticket UX |
| Incident Intelligence | Implemented E2E | Azure Monitor evidence adapter, topology/change correlation, evidence-backed RCA | richer App Insights/OTel queries and incident-system publishing |
| Drift Detector | Implemented E2E | Git/Terraform desired state + Azure Resource Graph observed state -> durable drift finding | corrective PR automation and more resource projections |
| Knowledge Decay Agent | Implemented reference | stale/ownerless/conflicting knowledge scoring | documentation PR/ticket publisher |
| Predictive change risk | Implemented reference | historical calibration, explicit confidence/evidence, deployment-risk output | real feature-store history and threshold calibration |
| Authoritative state | Implemented production adapter | SQLite contract plus Cosmos DB adapter with `_etag` CAS and app versions | multi-region policy/backup/retention operations |
| Audit | Implemented local contract | hash-chained audit and control-plane action audit | immutable external export/retention policy |
| Durable orchestration | Implemented | leases, retry/backoff, restart recovery, DLQ, durable remediation jobs | Service Bus/PostgreSQL production queue adapter |
| Mutation policy | Implemented | authoritative OPA contract, fail-closed client, OPA-native CI tests | bundle distribution/version promotion operations |
| Human approval | Implemented L3 primitive | exact plan-hash HMAC approval with expiry + Entra identity boundary | portal/Teams/Slack approval UX and approver-role mapping |
| Runbook library / AKS execution | Implemented reference | fixed typed runbooks, argv-only Kubernetes adapter, verify/rollback/escalation | more certified failure classes and Azure-resource actions |
| Digital twin | Implemented | ephemeral `eip-sim-*` Kubernetes sandbox, identity stripping, same adapter/verification, guaranteed cleanup | richer dependency replay and data fixtures |
| Self-healing loop | Implemented supervised | incident evidence -> plan -> durable approval -> OPA -> twin -> execute -> verify -> rollback/escalate -> audit | production runbook breadth and live operational drills |
| OpenTelemetry control-plane telemetry | Implemented | correlated plan/approval/twin/action/terminal telemetry, OTLP traces/metrics, SLO projection | dashboard packaging and alert thresholds |
| AI security/red-team | Implemented CI gate | poisoned evidence, policy bypass, secret exfiltration, ACL isolation, confused-deputy corpus | larger adversarial corpus and network-egress exercises |
| Supply-chain security | Implemented reference gate | exact dependency pins, CycloneDX-style SBOM, provenance digest, admission verifier, CI artifact | image signing/keyless attestation and cluster admission integration |
| FinOps / model economics | Partial/strong | token/search/tool usage events, cost rates, gateway budgets, OTel cost metrics | anomaly alerts and measured routing optimization |
| Executive control tower | Partial | KPI/ROI models plus live telemetry primitives | dashboard/API packaging and measured benefit lineage |
| Cross-cloud | Appropriate abstraction | provider contracts maintained | intentionally deferred until Azure depth is complete |
| L3 supervised autonomy | Implementation ready; evidence gate added | plan-bound approval, OPA, digital twin, rollback, kill-switch/error-mode primitives, evidence-bound certification report | execute and retain real service/environment/runbook drills |
| L4 bounded autonomy | Not certified | per-service/environment/runbook certification model and exercise evidence digest | real chaos evidence for every required control before promotion |

## What remains before production L3/L4 promotion

1. Execute real, retained exercises per service/environment/runbook for successful remediation, verification failure, rollback, kill switch, policy outage, audit outage and error-budget exhaustion.
2. Add broader certified runbooks for common Kubernetes/Azure failure classes with explicit preconditions, postconditions and rollback semantics.
3. Add immutable audit export plus production durable queue backend.
4. Package operational dashboards/alerts around the new control-plane metrics and SLO projection.
5. Integrate signed image attestations with cluster admission policy.
6. Calibrate predictive-risk and PR-Guardian thresholds against real deployment history.

## Promotion rule

No service moves to L3 or L4 because the implementation exists. Promotion is **service + environment + runbook specific** and requires a complete evidence set with no failed exercise, no missing evidence reference, no observed blast radius above the certified bound, independent verification, and security review. L4 additionally requires error-budget enforcement evidence and all bounded-autonomy controls.

## Acceptance rule

Every future PR must map to an original product capability and improve at least one measurable outcome: retrieval quality, developer workflow, change-risk precision, incident diagnosis, remediation safety, security, reliability or unit economics.
