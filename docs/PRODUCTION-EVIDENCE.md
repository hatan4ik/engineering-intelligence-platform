# Production Evidence Registry

| | |
|---|---|
| **Status** | Required evidence contract; no production readiness is implied by this document |
| **Owners** | Platform Engineering, SRE, Security, and the relevant service owner |
| **Applies to** | Any pilot using real organizational data and every L2–L4 capability |
| **Source plans** | [`PRODUCTION-PROOF-PLAN.md`](PRODUCTION-PROOF-PLAN.md), [`PRODUCTION-READINESS.md`](PRODUCTION-READINESS.md), [`../architecture/NFR.md`](../architecture/NFR.md) |

## Rule

Implementation, a green CI run, or a checked-in test fixture is not production evidence. Every
promotion decision requires retained, reviewable evidence from the actual certified scope:
service, environment, data source, model/prompt/policy version, and runbook where applicable.

The absence of an evidence record means **not proven**. It must not be inferred from a maturity
score or status label.

## Evidence record

Store one immutable record per exercise, integration run, or promotion decision in the approved
audit/evidence system. A GitHub Actions artifact may be an input, but cannot be the sole record.

| Field | Required content |
|---|---|
| `evidence_id` | Immutable unique identifier and content digest |
| `scope` | Repository/service, environment, region, tenant/data classification, and autonomy tier |
| `change` | Git SHA, image digest, IaC version, model/deployment, prompt, policy bundle, and runbook version |
| `claim` | Exact requirement or certification control being proven |
| `method` | Test, drill, shadow sample, restore exercise, or independently observed operational window |
| `result` | Pass/fail, quantitative result, timestamps, sampled population, and known limitations |
| `independence` | Identity of the verifier and why its signal is independent of the action path where required |
| `artifacts` | Signed links/digests for logs, traces, audit export, dashboards, and review record |
| `approval` | Service owner, Security/SRE reviewer, expiry, and exception/waiver reference if any |

## Minimum evidence by decision

| Decision | Minimum retained evidence |
|---|---|
| **Use real data in L0/L1 pilot** | Entra authentication; authorized and denied ACL tests; private-path evidence; source classification/retention; retrieval/citation/adversarial evaluation; operational SLO dashboard |
| **Enable PR Guardian advisory check** | Shadow sample with reviewer outcomes; precision/false-negative analysis by severity; citation review; cost/latency report; documented disable switch. Follow [`PR-GUARDIAN-SHADOW-PILOT.md`](PR-GUARDIAN-SHADOW-PILOT.md); an Actions artifact or PR comment alone is insufficient. |
| **Enable any blocking PR rule** | Advisory evidence plus service-owner approval, calibrated deterministic threshold, waiver/expiry procedure, rollback/disable drill, and monitored false-negative rate |
| **L3 remediation pilot** | All production-proof gates: durable state/queue, immutable audit export, OPA policy decision, digital-twin result where required, independent verification, rollback, kill switch, backup/restore, and retained drills |
| **L4 promotion** | Complete L3 evidence plus service/environment/runbook-specific certification, error-budget enforcement, repeated exercised evidence, and Security/SRE sign-off |

## Integration-proof minimum

The integration workflow must test the claim, not only reachability. The production-like suite
therefore needs to prove all applicable items below:

1. a valid Entra principal can access only its authorized evidence;
2. an unauthorized principal cannot retrieve, infer, or enumerate protected evidence;
3. a real source event is ingested idempotently and deletion/ACL change propagates;
4. a grounded query carries verifiable citations or refuses for insufficient evidence;
5. workflow state survives a worker restart and records policy/approval/audit decisions;
6. a denied action and an allowed action both write complete audit evidence; and
7. a rollback, kill switch, and dependency outage fail safely for the certified scope.

## Review and expiry

Evidence expires when the scoped service, environment, data classification, identity model,
model/prompt, policy, runbook, or infrastructure materially changes. An expired record reverts
the related capability to the previous safe autonomy tier until requalified.
