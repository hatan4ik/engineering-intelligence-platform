# Non-Functional Requirements

| | |
|---|---|
| **Status** | Target requirements; this document does not claim that they are deployed |
| **Owners** | Platform Engineering, SRE, Security, Data Governance |
| **Applies to** | Ingestion, AI gateway, PR Guardian, state/orchestration, remediation, and their Azure/AKS deployment |
| **Promotion rule** | A requirement is met only when its evidence is recorded in [`../docs/PRODUCTION-EVIDENCE.md`](../docs/PRODUCTION-EVIDENCE.md) |

## Purpose

Functional demonstrations are insufficient for a governed SDLC platform. These requirements make
the operational, data, and safety contracts explicit. They are intentionally stricter for a
control-plane or mutation path than for a read-only recommendation path.

## Requirements and evidence

| Area | Requirement | Evidence required before production use |
|---|---|---|
| **Identity and tenancy** | Every non-demo request has a verified workload or user identity. Tenant/repository/service authorization is evaluated before retrieval and before any workflow read/write. Header identity is never valid for real data. | Authn/authz integration test including denied cross-group and cross-repository requests; access-review record; service identity inventory |
| **Data lifecycle** | Each source has a classification, owner, purpose, retention period, residency decision, deletion/reconciliation path, and legal-hold rule. Search and embeddings remain rebuildable projections. | Source onboarding record; deletion propagation exercise; retention configuration; data-flow review |
| **Data lifecycle** | Each source has a classification, owner, purpose, retention period, residency decision, deletion/reconciliation path, and legal-hold rule. Search and embeddings remain rebuildable projections. Semantic caches must enforce a strict 24h TTL to satisfy GDPR "Right to be Forgotten" without surgical invalidations. | Source onboarding record; deletion propagation exercise; retention configuration; data-flow review |
| **Availability and degradation** | Read-only paths have published availability/latency objectives and fail with an explicit insufficient-evidence/dependency error. Mutation paths fail closed on any policy, audit, state, or verification dependency outage. | SLO definition, dependency-outage drill, alert/paging test, and retained telemetry window |
| **Durability and recovery** | Workflow state, approvals, jobs, and audit records use managed durable stores in production. Recovery objectives, backup cadence, restore procedure, and regional failure behavior are defined before L3. | Backup/restore drill within RPO/RTO, durable-queue restart exercise, audit-export integrity check |
| **Network and workload security** | Production uses private service access, controlled egress, least-privilege workload identity, hardened pods, network policy, and immutable image references. | IaC policy report, network reachability/egress test, workload-identity test, admission/signature verification |
| **Capacity and performance** | Load, concurrency, queue depth, backpressure, and dependency quotas are bounded. Each service has latency/error budgets and a load-shedding behavior. | Representative load/soak test, capacity model, quota validation, autoscaling and overload drill |
| **AI quality and safety** | Retrieval, citation, refusal, prompt-injection, and ACL-isolation quality are measured on versioned data. A change cannot silently degrade the certified baseline. | Versioned golden/adversarial set, threshold report, regression gate, reviewer sampling for live shadow traffic |
| **Observability and audit** | Every consequential decision is traceable by correlation ID across evidence, identity, model/version, policy, action, verification, cost, and outcome. Audit storage is immutable and separately retained from telemetry. | Trace-to-audit reconciliation, audit-write availability report, retention/export configuration, dashboard and alert test |
| **Cost and abuse protection** | Per-principal budget, rate/concurrency limits, input/output bounds, model routing, and anomaly alerts are enforced at the gateway. | Rate-limit/budget test, quota-exhaustion behavior, cost attribution and alert exercise |
| **Change management** | Infrastructure, policy bundles, prompts, model deployments, and runbooks are versioned, reviewed, promoted through environments, and reversible. | Promotion/rollback record, policy parity test, change approval and rollback drill |

## Service tiers

| Tier | Typical capability | Minimum operational posture |
|---|---|---|
| **Reference/demo** | Deterministic local API, fixtures, simulated runbooks | No real customer data; clearly marked non-production; no production authority |
| **L0/L1 production pilot** | Read-only evidence and recommendations | Identity/ACL/data-lifecycle/quality/observability requirements proven for the pilot scope |
| **L2** | Reviewable PR, ticket, or runbook proposal | L0/L1 controls plus named owner, operator workflow, and outcome capture |
| **L3** | Approved, low-risk non-production remediation | All relevant NFRs plus durable state/queue/audit, independent verification, rollback, and retained exercises |
| **L4** | Certified, bounded production remediation | All L3 requirements plus service/environment/runbook certification, error-budget enforcement, kill switch, and repeated retained evidence |

## Design constraints

- A search index, embedding store, model output, or dashboard is never the authoritative source
  for workflow state, approval, or audit.
- “Private endpoint exists” is not sufficient evidence of private end-to-end data flow.
- A green unit test or build does not prove availability, isolation, recovery, or production
  quality.
- NFRs are versioned alongside architecture and must be reviewed whenever a data source, model,
  runbook, or autonomy tier changes.
