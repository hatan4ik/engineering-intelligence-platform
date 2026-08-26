# Skill-Driven Documentation & Design Review

Applying the **Enterprise AI Transformation 22-Skill Operating Stack** to this repository's
product, process, and design documentation. Each applicable skill was run against the repo's
actual documents following its output specification and ruthlessness clause. Findings are
specific to the supplied documents; anything not traceable to a document is labelled
`[ASSUMPTION]`. Every audit ends with an **Operator Handoff** — what a human still owns.

**Reviewed at:** `main` @ `f598967` + safety-fix branch (PR #74).
**Framing note:** the pack is built for an *enterprise transformation* (org charts, SOPs,
frontline transcripts, vendor proposals). This repo is a *reference-implementation platform*
with rich design/process docs. The "AI workflow under audit" is therefore the platform's own
core workflows — supervised self-healing remediation, the RAG query path, and PR Guardian —
and the "current-state architecture" is the repo's own code and design docs.

---

## Part 1 — Coverage map (all 22 skills)

Legend: **Runnable** = repo supplies the skill's required inputs; **Partial** = some required
inputs present, others `[ASSUMPTION]`; **N/A** = requires enterprise inputs the repo cannot
supply (and shouldn't — it is a platform, not a deployed enterprise).

| # | Skill | Repo document that feeds it | Verdict |
|---|---|---|---|
| 01 | AI Readiness Assessment | design.md, threat-model, ingestion design; **no org chart** | Partial |
| 02 | Workflow Bottleneck Analysis | — (needs SOPs + frontline transcripts) | N/A |
| 03 | Use-Case Prioritization | roadmap, PROGRAM-BACKLOG (as candidate list) | Partial |
| 04 | Build vs Buy | design.md §11 already records this call (Azure OpenAI vs self-host) | Runnable (audit the existing call) |
| 05 | ROI Business Case | finops/cfo-roi-model.md | Runnable |
| 06 | Competitive Landscape | — (needs competitor earnings/postings) | N/A |
| 07 | Pilot Scoping | milestones/vertical-slice.md (as the pilot) | Partial |
| 08 | Stakeholder Mapping | governance/operating-model.md (roles only) | Partial |
| 09 | Architecture Audit | search_schema, topology, integrations/, adapters, app routes | **Runnable (deep)** |
| 10 | Change-Readiness | — (needs engagement surveys) | N/A |
| 11 | Target Operating Model | governance/operating-model.md | **Runnable (deep)** |
| 12 | Governance Framework | security-threat-model, autonomy tiers, PRODUCTION-READINESS | **Runnable (deep)** |
| 13 | Decision Rights | "AI recommends / policy authorizes / human approves" model | Runnable |
| 14 | Escalation Paths | control loop escalate, l4-certification | Runnable |
| 15 | Vendor Selection | design.md §11 (Azure chosen) | Partial (audit the call) |
| 16 | Sequencing Plan | roadmap, CAPABILITY-RECONCILIATION queue | Runnable |
| 17 | Pilot Charter | — (needs a specific named pilot + sponsor) | N/A |
| 18 | Production Gating | docs/PRODUCTION-READINESS.md, l4-certification | **Runnable (deep)** |
| 19 | Rollback Planning | control-loop rollback/escalate, digital_twin | Runnable |
| 20 | Adoption Tracking | — (needs usage telemetry from a live deployment) | N/A |
| 21 | ROI Attribution | finops/live_control_tower (fixtures only, not live) | N/A (not launched) |
| 22 | Retraining Cadence | runtime-observability, drift | Runnable |

**Coverage headline:** the repo's documentation is strongest exactly where this platform's thesis
lives — **governance, production-gating, architecture, operating model** (all deep-runnable) — and
absent exactly where a *deployed* enterprise would have evidence (adoption, ROI attribution,
change-readiness). That is the correct shape for a pre-deployment reference platform, and it is
also the honest boundary: **every "measurable outcome" skill (10, 20, 21) is N/A because nothing
is in production yet.** The docs should not claim outcomes they cannot yet have.

---

## Part 2 — Deep audits

### Skill 12 — Governance Framework (persona: CISO; kills hand-waving)

**Input used:** `governance/security-threat-model.md`, design.md §6 + autonomy ladder,
`docs/PRODUCTION-READINESS.md`.

**Step 1 — Risk-tiering.** The repo has an autonomy ladder (L0–L4/L5) which is a *capability*
ladder, but **not the skill's risk tier** (data-sensitivity × decision-impact). Mapping the
platform's own workflows onto the skill's tier matrix:

| Workflow | Data sensitivity | Decision impact | Skill-12 tier |
|---|---|---|---|
| RAG query / PR Guardian | Confidential (source code, ACL-trimmed) | Operational | **Tier 2** |
| Incident RCA / drift | Confidential | Operational (advisory) | **Tier 2** |
| Supervised self-healing (prod remediation) | Confidential | **Autonomous consequential** (mutates prod with human approval) | **Tier 3 + formal review** |

**Finding G-1 `[gap]`.** The repo governs by *autonomy level* but never cross-references it to a
**data-sensitivity × decision-impact tier**. The threat model is control-complete but the
governance doc does not state, per workflow, *which tier it is and therefore which controls are
mandatory*. Remediation surfaces (self-healing) are correctly the strictest in code, but the
governance **document** does not derive that from a tiering — it asserts it. A CISO signing this
needs the derivation, not the assertion.

**Step 3 — Audit-logging per tier.** The repo has a hash-chained audit log (`state/audit.py`)
with actor/action/resource/payload and correlation IDs — **strong**, and it maps to most of the
skill's Tier-3 log-element table. **Gaps against the spec:** the log element *"confidence / scores"*
is not captured for agent decisions; *"data sources retrieved"* (which evidence chunks fed a
decision) is captured as evidence IDs on incident hypotheses but **not on the RAG answer path**;
*"tamper-evidence"* is present (hash chain) but *"access to logs (who, how)"* is undefined in any
doc. → three named log-capture gaps.

**Step 4 — Model approval workflow.** DESIGN + PRODUCTION-READINESS define a promotion/certification
gate, but the skill's **"submission package"** (use-case description, tier classification, eval
results, data-handling confirmation, logging confirmation, HITL design, rollback reference, cost
projection) is **not enumerated as a required artifact set** anywhere. The repo has all the
*pieces* but no single "here is what you submit to get a model approved for production" checklist.

**Verify-before-acting:** a real CISO / privacy officer must confirm data-residency and
vendor-data-use terms (Azure OpenAI zero-retention) — the docs *assert* tenant isolation but cite
no executed contract clause. `[ASSUMPTION]` that the enterprise agreement is in force.

**Operator Handoff (Skill 12):** (a) add a per-workflow tier derivation to `governance/`;
(b) close the three audit-log element gaps (confidence, RAG evidence lineage, log-access policy);
(c) write the one-page model-approval submission package; (d) obtain and cite the vendor
data-use contract clause.

---

### Skill 18 — Production Gating (persona: release gatekeeper; "no graduation with any Fail")

**Input used:** `docs/PRODUCTION-READINESS.md`, `architecture/l4-certification.md`,
CAPABILITY-RECONCILIATION promotion rule.

The repo's PRODUCTION-READINESS doc already thinks in gates (5 certification gates + L0–L4 table),
which is **unusually mature**. Audited against the skill's five dimensions:

| Skill-18 dimension | Repo coverage | Gate status against spec |
|---|---|---|
| Performance | eval harness exists but does **not** drive the real retriever (board finding P-F2); no load-test artifact | **Fail** — no accuracy evidence at volume |
| Security & governance | threat model, OPA policy, red-team CI corpus | **Partial** — controls exist; but OPA is not wired into the loop by default (board finding R-F3), so the "model approval signed / policy enforced" gate lacks live evidence |
| Operational readiness | rollback + escalate in control loop; digital twin | **Partial** — rollback exists but the skill demands it be **rehearsed in non-prod with a dated log**; the repo's soak/evidence harness records *shape not truth* (board finding R-F6) |
| Adoption readiness | — | **Not assessed** — correctly N/A pre-deployment |
| Financial controls | cfo-roi-model, gateway budgets, cost telemetry | **Partial** — budget is an env constant not reconciled to token counts (board finding S-F8); no finance sign-off artifact |

**Finding GATE-1 `[critical]`.** By the skill's own rule — *"no graduation with any Fail; do not
mark Pass without an artifact"* — the platform **cannot graduate any workflow to production
today**, and the repo's own CAPABILITY-RECONCILIATION already says exactly this ("No service moves
to L3/L4 because the implementation exists"). The two documents **agree**, which is a strong
consistency signal. The divergence is subtler: PRODUCTION-READINESS presents its gates as
*present and passable*, while the skill forces the **evidence** column — and there the board
review found the evidence harness validates shape, not truth. So: **the gate structure is
production-grade; the evidence behind three gates is not yet real.**

**Finding GATE-2 `[gap]`.** The skill mandates a **30-day hypercare period with exit criteria**
after graduation. No repo document defines hypercare. This is a genuine hole in an otherwise
complete gating story.

**Operator Handoff (Skill 18):** (a) make the eval harness drive the real retriever and gate CI
(already PR-10 in the board plan); (b) produce the three missing evidence artifacts (load test,
rehearsed-rollback log with date, finance sign-off); (c) add a hypercare definition;
(d) reconcile the budget guardrail to actual token spend.

---

### Skill 11 — Target Operating Model (persona: ops designer; roles must change concretely)

**Input used:** `governance/operating-model.md`.

**Finding TOM-1 `[gap]`.** `operating-model.md` is a **governance/ownership** doc (council, core
team, release gates, decision rights) — it is a good Skill-13 input but it is **not a Target
Operating Model** in the Skill-11 sense. The skill demands four artifacts the doc does not contain:

1. **Role evolution** — which existing roles change and *exactly how daily tasks shift from
   execution to validation*. The doc lists roles (AI Platform Architect, SRE rep, FinOps partner)
   but never states how, e.g., an SRE's day changes when the platform proposes remediations.
2. **Net-new roles** — the doc names a team but does not identify which roles are **new** vs
   reassigned (e.g., "Retrieval/evaluation engineer" appears new; not flagged as such).
3. **Handoff map** — every AI→human and human→AI touchpoint. The *code* has these (approval gate,
   escalation) but no **document** enumerates them as an operating-model handoff map.
4. **Human-in-the-loop protocol for edge cases** — DESIGN describes escalation, but the
   step-by-step "when the AI defers, exactly who does what within what SLA" is not written as a
   TOM protocol.

**Consistency check:** the code encodes a *stronger* operating model (typed phases,
approve/escalate) than the document describes. This is the recurring theme of the whole repo,
now visible from the process side too: **implementation leads documentation.**

**Operator Handoff (Skill 11):** author a real TOM section — role-evolution table (before/after
daily tasks), net-new-role flags, the AI↔human handoff map (extractable directly from the control
loop), and the HITL edge-case protocol with SLAs.

---

### Skill 09 — Architecture Audit (persona: staff data engineer; find the production surprises)

**Input used:** `ingestion/search_schema.py`, `topology/`, `integrations/`, `app/` routes,
adapters; DESIGN §5.

This audit **strongly corroborates the earlier board review** from a data-engineering angle:

**Step 3 — Missing data vectors.** The RAG workflow requires vector embeddings on every chunk; the
board review found **no production path computes embeddings** (P-F3) — chunks are indexed with
empty vectors against a schema that mandates the field. In Skill-09 terms this is a *missing data
vector*: the "semantic similarity" input the workflow depends on **lives nowhere**.

**Step 4 — Structure deficits.** Organizational memory (`KnowledgeChunk`) lacks the `source`/
`embedding` fields the retrievers `select` (board finding P-F7), so unstructured org knowledge
**cannot be vector-searched or cited** — a structure deficit that caps the "one trimming
mechanism" claim.

**Step 5 — Latency risks.** `[gap]` **No repo document records a single latency or throughput
number.** Skill 09 requires observed latency per vector and flags "chained calls whose summed
latency exceeds the user-facing budget." The self-healing loop chains: retrieve → LLM synthesize →
policy → simulate (twin provision + kubectl) → execute → verify. That is a long chain with **no
documented latency budget** and a lease (60s) the board found shorter than a single
simulate+execute pass (R-F2). This is the sharpest *new* finding this lens adds: **the platform
has no documented latency model, and the one implicit budget (the job lease) is mis-sized.**

**Step 6 — Security/access path.** Strong: Managed Identity, argv-only adapters, ACL-in-search.
The one gap the board already named: the ingestion-minted `repo:X:read` ACL vocabulary has no
resolver mapping to real Entra group claims (S-F5), so the access path is *documented* but
*unexercised end-to-end*.

**Operator Handoff (Skill 09):** (a) publish a latency/throughput budget per workflow step and
size the job lease from it; (b) wire embeddings (board PR-9); (c) give KnowledgeChunk the
retrievable fields; (d) build the claims→ACL resolver.

---

## Part 3 — What the skillset says about the documentation as a whole

Three cross-cutting patterns, each traceable to specific documents:

1. **Implementation leads documentation, everywhere.** Skills 11, 12, and 09 each independently
   found the *code* encodes a stronger, more complete model than the *document* describes (TOM,
   audit-logging, handoff map). The docs are not wrong; they are **behind**. For a platform whose
   thesis is "grounded, evidence-backed," the documentation should not be the least-evidenced
   artifact.

2. **The repo is honest about outcomes it cannot have.** Every outcome-measurement skill (10, 20,
   21) is genuinely N/A because nothing is deployed, and the repo's own reconciliation says so.
   This is the single most credible thing about the documentation: it does **not** fabricate
   adoption or ROI-attribution evidence. Hold that line.

3. **The gate structure is production-grade; the evidence is not yet real.** Skills 12 and 18 both
   land here, and it converges exactly with the earlier engineering board review (evidence
   harnesses validate shape, not truth). The documentation's job now is not more gates — it is
   **making three or four specific evidence artifacts real** (eval-at-volume, rehearsed rollback,
   finance sign-off, latency budget).

## Consolidated Operator Handoff (the real work list)

| # | Action | Skill | Owner (repo role) |
|---|---|---|---|
| 1 | Per-workflow data-sensitivity × decision-impact tier derivation | 12 | Security/Governance lead |
| 2 | Close 3 audit-log element gaps (confidence, RAG evidence lineage, log-access policy) | 12 | SRE/Observability |
| 3 | One-page model-approval submission package | 12 | AI Platform lead |
| 4 | Publish latency/throughput budget per workflow step; resize job lease | 09 | Platform/DevOps |
| 5 | Rehearsed-rollback log + hypercare definition | 18/19 | SRE |
| 6 | Real TOM section: role-evolution table + handoff map + HITL protocol | 11 | Product/DevEx owner |
| 7 | Reconcile budget guardrail to token spend; finance sign-off | 18/05 | FinOps partner |
| 8 | Obtain + cite vendor data-use contract clause | 12 | Legal/Procurement |

Items 4, 5, 7 and the embedding/ACL fixes are already tracked in the engineering board plan
(PR-9, PR-10, PR-11, PR-12); items 1, 3, 6, 8 are **documentation/process work** this skill-driven
review adds on top.
