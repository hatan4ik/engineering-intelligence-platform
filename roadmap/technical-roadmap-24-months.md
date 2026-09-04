# Outcome-Gated Product Maturity Roadmap

| | |
|---|---|
| **Classification** | Target proposal — delivery sequence, not a production claim |
| **Owner** | Engineering Intelligence lead + Developer Experience |
| **Reviewed** | 2026-09-03 against `origin/main` at `f556e16`; no stage exit claimed |
| **Active product** | [PR Guardian](../docs/PRODUCT-STRATEGY.md) for one or two named repositories |
| **Authoritative current state** | [Current Position](../docs/CURRENT-POSITION.md) |
| **Evidence standard** | [Production evidence contract](../docs/PRODUCTION-EVIDENCE.md) |
| **Terminology** | [Company Brain Glossary](../docs/GLOSSARY.md) |

## Decision

The platform will reach high maturity by proving one valuable engineering workflow before it
expands to other workflows or autonomy tiers. The first product is **<span title="Pull Request">PR</span> Guardian**. It remains
shadow-only until its repository-specific evidence supports an advisory decision; no roadmap
phase alone authorizes enforcement, production mutation, <span title="Autonomy Level 3 — approve and execute">L3</span>, or <span title="Autonomy Level 4 — bounded autonomous">L4</span>.

The time ranges below are planning horizons, not delivery promises. A failed exit gate returns the
work to the preceding stage; it does not justify moving ahead on a different feature track.
No Azure, AKS, private-environment, or production proof is scheduled by this implementation
roadmap.

## Product operating model

```text
GitHub event / trusted publisher
        |
        v
<span title="Pull Request">PR</span> Guardian product workflow ──> Finding + evidence + simulated policy
        |                                      |
        v                                      v
Repository configuration                  Reviewer disposition
        |                                      |
        `──────────────> durable outcome/evaluation record
                                            |
                                            v
                                calibrated advisory decision
```

The product uses three bounded contexts:

1. **Product workflow** — repository onboarding, <span title="Pull Request">PR</span> findings, evidence presentation, feedback,
   waivers, and product metrics. `product/` owns use cases; `integrations/` owns GitHub/<span title="Azure DevOps">ADO</span>
   adapters.
2. **Knowledge platform** — source lifecycle, ACLs, provenance, retrieval, and service graph.
   It provides evidence; it does not decide a merge outcome.
3. **Trust and control** — identity, audit, policy, workflow state, telemetry, and later approval
   mechanics. It constrains the product; it is not itself a customer product surface.

Incident, deployment, drift, and remediation modules remain reference verticals until they reuse
these product contracts and have their own explicit discovery decision. They must not compete
with PR Guardian for the first pilot's scope.

## Current baseline

| Area | Repository state | Maturity implication |
|---|---|---|
| <span title="Pull Request">PR</span> Guardian | Read-only/shadow workflow split; repository-owned `shadow` / `advisory` / `enforce` modes with owner approval, expiry, waivers, and a kill switch; trusted publisher is the only writer; Architecture Guard on the <span title="Pull Request">PR</span> path; shadow-only onboarding, readiness, and bootstrap tools | A **mode-capable shadow product** — advisory or enforce is a repository owner's decision, and no repository has made it |
| Feedback | Reviewer labels, a closure report that computes a real decision, calibration as a recommendation, a scheduled report workflow | Calibration numbers are recommendations until a named repository accumulates ≥30 classified observations |
| Knowledge | Runtime ingestion trigger (CLI + workflow) over the governed pipeline; evidence registry; fail-closed integration proof | Still unproven against a real Azure index; the registry is empty by design |
| Control plane | `temporal` mode constructible over Cosmos; opt-in remediation workflow with plan-hash approval; <span title="Autonomy Level 1 — recommend">L1</span>/<span title="Autonomy Level 2 — human execute">L2</span> operations routes | The worker remains evidence-only by default; consequential activities stay behind the flag and are unproven |
| Rehearsal and certification | Soak, readiness, and <span title="Autonomy Level 3 — approve and execute">L3</span> exercise runners; scoped <span title="Autonomy Level 4 — bounded autonomous">L4</span> eligibility and an executor/<span title="Open Policy Agent">OPA</span> gate that refuses uncertified <span title="Autonomy Level 4 — bounded autonomous">L4</span> | Simulated exercises are `rehearsal` grade and never count; nothing is certified |

Reference paths exist across later stages, but no stage's engineering exit criteria should be
considered complete merely because a source path exists. The evidence half of no stage has been
earned. [`../docs/CURRENT-POSITION.md`](../docs/CURRENT-POSITION.md) is the authoritative
per-stage source/evidence table.

## Delivery timeline and gates

### Stage 0 — Product truth and pilot foundation (0–2 weeks)

**Outcome:** one truthful product boundary and a reproducible repository baseline.

- Define and version the canonical `RepositoryConfig`, `PRFinding`, `EvidenceBundle`, `Outcome`,
  and `EvaluationRun` contracts.
- Keep GitHub/<span title="Azure DevOps">ADO</span>/PagerDuty-style concerns in `integrations/`; organize only <span title="Pull Request">PR</span> Guardian beneath a
  vertical `product/pr_guardian/` boundary as it grows. Do not perform a broad repository rewrite.
- Make documentation links/anchors a required CI gate and set a documentation authority order.
  The unreferenced `src/` prototypes and `providers/` stubs were retired; their concepts live in
  `app/` and the target-state architecture documents.
- Reconcile the capability matrix, scorecard, and roadmap whenever a material reference slice is
  added.
- Define named pilot repositories, service owners, source access model, data classification,
  kill switch, and the baseline metrics collection plan.

**Exit:** schemas have contract tests; CI protects the documentation and product contracts; each
pilot repository has an owner and an explicit non-enforcement configuration.

### Stage 1 — PR Guardian pilot-ready shadow product (2–6 weeks)

**Outcome:** every material PR finding can be understood and later evaluated.

- Persist idempotent PR findings and evidence references outside an Actions workspace.
- Join deterministic diff/service/blast-radius analysis with **authorized** retrieved evidence;
  show citations, policy version, source freshness, and an insufficient-evidence result.
- Add repository-specific configuration for service ownership, path mapping, risk factors,
  enabled evidence sources, and retention.
- Record explicit reviewer disposition: confirmed risk, false positive, useful, not useful, or not
  reviewed. A lack of action is never automatically a false positive.
- Build an offline golden corpus from approved historical <span title="Pull Request">PR</span> material and gate deterministic rules,
  evidence access, and schema compatibility in <span title="Continuous Integration">CI</span>.

**Exit:** a product owner can inspect a single durable PR record end-to-end—event, finding,
evidence, policy simulation, reviewer disposition, cost/latency, and correlation ID—without
claiming an enforcement decision.

### Stage 2 — Measured advisory decision (6–12 weeks)

**Outcome:** owners decide whether non-blocking PR Guardian is useful for a named repository.

- Export pilot outcomes to the approved retained evidence store; short-lived GitHub artifacts are
  not the system of record.
- Correlate merged PRs to independent, post-merge signals such as rollback, failed deployment,
  or incident only when source identity and causal uncertainty are retained.
- Review precision, observed false-negative rate, citation correctness, ACL failures, reviewer
  utility, latency, and unit cost by service and severity—not as a blended platform average.
- Version risk thresholds and evaluation datasets. Threshold changes are reviewed product/policy
  changes, never automatic model tuning.
- Add a compact API or portal evidence view only after the GitHub surface and evidence store are
  usable; avoid building a generic chat interface.

**Exit:** repository owners, Security, and Developer Experience approve an evidence review. The
only permitted promotion is a **non-blocking advisory** check for the certified repository scope.
Failure returns to shadow mode.

### Stage 3 — PR Intelligence V2 and Architecture Guard (3–6 months)

**Outcome:** PR Guardian becomes a repeatable developer product rather than a one-off workflow.

- Expand to 2–5 repositories only with isolated configuration, access control, cost attribution,
  and service-owner onboarding.
- Add finding lifecycle, deduplication, waivers with expiry/reason/owner, and a tested disable
  switch. A waiver cannot weaken retrieval ACLs or mutation policy.
- Add richer dependency, ownership, delivery, and authorized historical-regression evidence.
- Deliver Architecture Guard as a second product use case on the same finding/evidence/outcome
  contracts—not as a parallel agent stack.
- Consider a narrowly deterministic blocking rule only after the repository-specific evidence
  gate in [Product Strategy](../docs/PRODUCT-STRATEGY.md) is met.

**Exit:** use and utility are measured across multiple services, findings are stable and
reviewable, and any proposed enforcement condition has a waiver, expiry, disable drill, and an
owner-approved deterministic threshold.

### Stage 4 — Operations intelligence at L1/L2 (6–12 months)

**Outcome:** incidents and releases gain the same evidence discipline without autonomous action.

- Correlate code, deployment, telemetry, incident, ownership, and runbook evidence through the
  shared graph and evidence contracts.
- Introduce incident and deployment intelligence as **observe/recommend** workflows first.
- At <span title="Autonomy Level 2 — human execute">L2</span>, prepare exact, reviewed runbook or corrective-<span title="Pull Request">PR</span> proposals. Humans execute; the system
  has no production mutation authority.
- Measure hypothesis correctness, time to disposition, avoided rework, evidence quality, and the
  operational cost of every product workflow.

**Exit:** an L1/L2 operational workflow has independently reviewed outcome evidence and uses the
same identity, audit, policy, evidence, and lifecycle contracts as PR Guardian.

### Stage 5 — Rehearsed remediation and narrow L3 candidates (12–18+ months)

**Outcome:** a small number of reversible runbooks can be considered for human-authorized action.

- Rehearse candidate runbooks in an isolated digital twin with representative fixtures and
  independent verification. A digital twin is validation evidence; it is not an autonomy tier.
- Demonstrate idempotency, bounded blast radius, timeout/retry/compensation, rollback,
  kill-switch, policy outage, audit outage, and error-budget behavior.
- Retain immutable audit, durable state/queue, restore-drill, security, and operational evidence
  for the **service + environment + runbook** combination.
- Grant <span title="Autonomy Level 3 — approve and execute">L3</span> only when a human approval authorizes the exact, plan-bound, allow-listed action.

**Exit:** a scoped L3 certification packet meets the production evidence contract. No other
service, environment, or runbook inherits that authorization.

### Stage 6 — Bounded L4 autonomy (only after Stage 5 evidence)

**Outcome:** a certified low-blast-radius runbook may execute automatically inside strict limits.

<span title="Autonomy Level 4 — bounded autonomous">L4</span> requires repeated <span title="Autonomy Level 3 — approve and execute">L3</span> evidence plus service-specific error-budget enforcement, <span title="Open Policy Agent">OPA</span> policy,
independent verification, rollback, immutable audit, kill-switch proof, and recurring failure
exercises. A generic success-rate target is insufficient. L5 remains unsupported.

## Quality gates that apply now

- No blocking PR rule based on an LLM-derived recommendation alone.
- No evidence crosses an ACL boundary; missing or stale evidence is an explicit limitation.
- No “merged,” “ignored,” or “closed” PR status is silently classified as a correct or incorrect
  finding.
- No product outcome is called measured without retained source lineage and scope.
- No L3/L4 feature work displaces the active PR Guardian quality, feedback, or evidence gates.

## Explicit deferrals

Until Stage 3 has passed its product gates, defer broad source onboarding, generic engineering
chat, IDE productization, multi-cloud expansion, production remediation, organization-wide
rollout, and a control-tower-first user experience. These are target-platform capabilities, not
the path to early product maturity.
