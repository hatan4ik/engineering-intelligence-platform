# Architecture & Implementation Review — Internal AI Ecosystem

**Reviewed:** `main` @ `faa1ba4` (merge of PR #13, "M3: production ingestion, AST chunking and ACL propagation")
**Date:** 2026-08-21
**Frame of reference:** the internal-AI-ecosystem model — Phase 1 knowledge ingestion, Phase 2 RAG engine, Phase 3 agentic SDLC integration — plus the build-vs-buy position that the RAG plane and agents are built in-house while inference is routed through an enterprise provider under tenant isolation.

---

## 1. Verdict

The strategic position of this repository is right, and it is unusually well-argued: the control model (*AI recommends, deterministic policy authorizes, allow-listed automation executes, verification closes the loop*) is exactly the invariant that separates a self-healing platform from an outage generator. The autonomy tiers in `governance/security-threat-model.md`, the certification gates in `docs/PRODUCTION-READINESS.md`, and the retrieve-then-reason boundary in `app/main.py` are the correct primitives, and the build-vs-buy call — Azure OpenAI + Managed Identity rather than self-hosted foundation models — matches what scaled engineering organizations actually do.

The problem is not the architecture. It is that **the repository's verification loop has never once run green**, and behind that broken loop the implementation has drifted into a state where several load-bearing claims are not true of the code.

Concretely, as of `faa1ba4`:

- All 19 CI runs in the repository's history have failed. Not one has passed.
- `pytest` cannot collect a single test module in CI. Every test in the repo is unrun.
- The `ingestion/` package merged in PR #13 contains two mutually incompatible generations of its own domain model; three of its eleven modules cannot be imported at all.
- The retrieval authorization boundary — the control that the entire IP-protection argument rests on — is a self-asserted, unauthenticated HTTP header that defaults to a privileged group when omitted.
- The ingestion plane writes an index schema that the query plane cannot read.

None of these are visible from reading the documentation, which is uniformly excellent. That gap between documented and actual is itself the most important finding: a platform whose value proposition is *grounded, evidence-backed answers* is currently making unverified claims about itself.

**Assessment against the three-phase model:**

| Phase | Documented | Actually implemented | State |
|---|---|---|---|
| 1 — Knowledge ingestion | Event-driven incremental ingestion, ACL propagation, AST chunking, embed + index, delete reconciliation | Event normalization, AST/text chunking, in-memory + Azure index adapters. No embeddings. Durable ledger/worker/loaders present but non-importable. | Partial, partly broken |
| 2 — RAG engine | Authorize → retrieve → security-trim → synthesize with citations | Correct shape and ordering. Authorization is unauthenticated. Read/write schema mismatch. No vector retrieval. | Shape correct, controls not enforced |
| 3 — Agentic SDLC | PR Guardian, deploy-failure RCA, drift detection, remediation agent, policy gate | Deterministic control loop with approval/escalation is real and tested-in-intent. All four agents are empty stubs. OPA policy is never evaluated by any code path. | Control loop real, agents absent |

The honest summary: **Phase 2's skeleton is real and well-shaped; Phase 1 is half-built and currently self-inconsistent; Phase 3 exists as a state machine plus placeholders.** The repository is a strong blueprint with a partial vertical slice — which is a perfectly respectable place to be. It is presented, however, as a validated reference implementation, and that specific claim does not hold.

---

## 2. Findings

Severity ordered. Each finding is reproducible from the cited files.

### P0-1 — CI has never passed; no test in this repository has ever run

19 of 19 runs of `Reference Implementation CI` concluded `failure`, including every run on `main`. The most recent (`32526256425`, `main`) fails at collection:

```
tests/test_control_loop.py:1: in <module>
    from app.agents.control_loop import ControlLoop, Incident, Phase
E   ModuleNotFoundError: No module named 'app'
!!!!!!!!!!!!!!!!!!! Interrupted: 7 errors during collection !!!!!!!!!!!!!!!!!!!!
```

**Root cause.** There is no `conftest.py`, `pytest.ini`, `pyproject.toml`, or `setup.cfg` at the repository root, so the repository root is never placed on `sys.path`. `pytest -q` (what CI runs) therefore cannot import `app` or `ingestion`. The failure is invisible locally to anyone who runs `python -m pytest`, which *does* prepend the working directory — the two commands are not equivalent, and the README documents the one that works while CI runs the one that does not.

`python demo/aks/scenario_runner.py` (step 3 of the CI job, and a documented Quick Start command) fails identically, for the same reason.

**Consequence.** Every correctness claim in the README, `architecture/milestones/milestones/vertical-slice.md`, and `docs/PRODUCTION-READINESS.md` Gate 1 is unverified. The Dependabot PR (#2, pytest 9.0.3) is red for this reason and not for its own. This is the single highest-leverage fix in the repository: it is roughly four lines and it converts the entire test suite from decorative to load-bearing.

**Fix.**

```toml
# pyproject.toml (new, repository root)
[tool.pytest.ini_options]
pythonpath = ["."]
testpaths = ["tests"]
```

and in `.github/workflows/ci.yml`, run the scenario runner as a module:

```yaml
- run: python -m demo.aks.scenario_runner
```

(with `demo/__init__.py` and `demo/aks/__init__.py` added), or set `PYTHONPATH: .` at job level. Then fix what the now-running tests reveal — see P0-2.

### P0-2 — `ingestion/` contains two incompatible generations of its own domain model

PR #13 merged modules written against two different, mutually exclusive APIs.

*Generation B* (the one `models.py` actually defines): `SourceIdentity`, `FileChange`, `ACL`, `Chunk`, `NormalizedEvent`, `IngestionPipeline`, `Index`/`InMemoryIndex`, `AzureSearchIndex`.

*Generation A* (referenced but no longer defined anywhere): `SourceDocument`, `IngestionEvent`, `IngestionProcessor`.

Three modules import names that do not exist and therefore raise `ImportError` on import:

- `ingestion/providers.py:9` — `from .models import SourceDocument`
- `ingestion/ledger.py:9` — `from .models import IngestionEvent`
- `ingestion/worker.py:7-8` — `from .models import IngestionEvent`, `from .pipeline import IngestionProcessor` (`pipeline.py` defines `IngestionPipeline`)

Two test modules are written entirely against the dead API and can never pass: `tests/test_ingestion_worker.py` and `tests/test_ingestion_ledger.py` (both construct `IngestionEvent(...)` / `SourceDocument(...)`).

The practical loss is significant: the durable SQLite ledger with DLQ semantics, the GitHub App and Azure DevOps file loaders — the three things `docs/INGESTION.md` lists as the top production follow-ons — **are already written**, and are sitting in the tree unreachable. `IngestionPipeline.processed_events` remains an in-memory `set`, so idempotency does not survive a restart, while `ledger.py` implements exactly the durable replacement.

**Fix.** Adopt Generation B as canonical and port the three orphans onto it: `SourceDocument` → `FileChange`+`SourceIdentity`, `IngestionEvent` → `NormalizedEvent`, `IngestionProcessor` → `IngestionPipeline`. Rewrite the two dead test modules against the same. Then wire `IngestionWorker`/`SqliteEventLedger` in front of `IngestionPipeline` and delete the in-memory `processed_events` set. This is a half-day of work that recovers a merged-but-lost PR.

### P0-3 — The retrieval authorization boundary is unauthenticated and fails open

`app/main.py`:

```python
def authorized_groups(raw: str | None) -> list[str]:
    return [g.strip() for g in (raw or "engineering").split(",") if g.strip()]
```

Group membership is taken verbatim from the client-supplied `X-EIP-Groups` header. There is no authentication, no token validation, no identity at all. Any caller who can reach `/v1/query` can assert any group and retrieve any chunk indexed under it. When the header is absent, the caller is silently granted the `engineering` group — a fail-open default on the exact control that the IP-protection argument depends on.

This directly contradicts three stated invariants: `governance/security-threat-model.md` ("Authenticate every caller with Entra ID; authorize before retrieval"), `architecture/milestones/milestones/vertical-slice.md` invariant 1, and `docs/PRODUCTION-READINESS.md` Gate 2. The *ordering* is right — authorization precedes retrieval, which is the hard part to retrofit — but the authorization itself is not enforced.

**Fix.** Validate an Entra ID bearer token and derive groups from token claims (`groups` / `roles`), never from a request header. Fail closed with `401` when no valid token is present. Keep the header path, if at all, behind an explicit `EIP_ALLOW_HEADER_IDENTITY=true` dev-only flag that refuses to start when `EIP_BACKEND=azure`. Add a test asserting that an unauthenticated request retrieves nothing.

Related: `acl_users` is written by ingestion (`ingestion/models.py`, `ingestion/schema.py`) but never consulted at query time (`app/rag/azure_backend.py:_acl_filter` filters on `acl_groups` only), so user-scoped grants are silently unenforceable.

### P1-4 — The ingestion plane writes an index schema the query plane cannot read

`ingestion/schema.py` defines fields `path`, `repository`, `document_id`, `symbol`, `ordinal`, `acl_groups`, `acl_users`. `app/rag/azure_backend.py:retrieve()` does:

```python
filters.append(f"repo eq '{...}'")
...
select=["source", "content"],
```

There is no `source` field and no `repo` field in the index the ingestion pipeline builds. Against a real index, a repo-scoped query fails on an unknown filter field, and every unscoped result returns `source="unknown"` — which then propagates into the "cite source paths" prompt and the user-visible citations. The README's Azure-mode section documents the *old* contract (`source`, `content`, `repo`, `acl_groups`), so all three artifacts disagree.

**Fix.** One schema module owns the contract. Map `source` → `path` and `repo` → `repository` in the query path (or add computed aliases at index time), and derive the README's field list from the schema rather than restating it.

### P1-5 — In-memory and Azure indexes implement different ACL semantics

`ingestion/index.py:InMemoryIndex.search()` requires a group match **and** a user match when a chunk carries both, and treats a chunk with an empty ACL as visible to everyone. `ingestion/azure_search.py:AzureSearchIndex.search()` ORs the group and user clauses, and — because an empty caller ACL yields the literal filter `"false"` — treats an empty ACL as visible to no one.

The two backends are opposite in both respects. Tests exercise the in-memory one; production runs the other. A chunk indexed with no ACL is world-readable in test and invisible in production; a chunk with both group and user ACLs is more permissive in production than any test asserts.

**Fix.** Extract one authorization predicate and have both backends implement it, then run a single conformance suite against both (parametrized over the `Index` protocol). Decide explicitly whether an empty ACL means public or private — and fail closed.

### P1-6 — The OPA policy is never evaluated, disagrees with the control loop, and its tests target a different package

Four separate problems in the policy layer:

1. **No code path evaluates it.** `app/agents/control_loop.py` hardcodes its own allow-list in Python. `infra/policy/remediation-policy.rego` is not consulted by the API, the control loop, the scenario runner, or CI. The "deterministic policy authorizes" invariant is currently implemented as a Python `set` literal.
2. **The allow-lists are disjoint.** Control loop: `{"restart-deployment", "rollback-deployment", "scale-out"}`. Policy: `{"restart_workload", "rollback_last_release", "rotate_expired_certificate"}`. No runbook name appears in both. Whichever is authoritative, the other is wrong.
3. **Environment naming disagrees.** Control loop compares `environment == "prod"`; policy compares `input.environment == "production"`. A policy check against a control-loop incident would fall through to the non-production rule.
4. **The policy tests test nothing.** `infra/policy/remediation_policy_test.rego` declares `package eip.remediation`, while the policy is `package engineering_intelligence.remediation` — so `allow` is undefined in the test's scope. The tests also omit `audit_enabled` and `verification_defined`, which the policy requires, and use pre-v1 Rego syntax (`test_x { ... }` without `if`) against a policy written in v1 syntax (`allow if { ... }`). CI never runs `opa test`, so none of this surfaced.

**Fix.** Make OPA the single source of truth: one `runbooks.rego` data document consumed by both the policy and (via export) the control loop; align environment vocabulary; move the tests into the policy's package with complete inputs; add `opa test infra/policy` and `opa check --v1-compatible` to CI. Then have `ControlLoop.POLICY` actually call the policy engine rather than re-deciding in Python.

### P1-7 — The evaluation harness fabricates its results

`eval/evaluate.py` does not call any retriever. It hardcodes the result set:

```python
retrieved = ['architecture/self-healing.md', 'roadmap/technical-roadmap-24-months.md']
```

`architecture/self-healing.md` does not exist in the repository (the file is `architecture/azure-devops-self-healing-reference.md`), and the actual `InMemoryRetriever` in `app/main.py` returns different sources. The harness prints `precision@3: 0.5, recall@3: 1.0` as measured numbers; they are arithmetic over a literal. CI runs this and treats a zero exit as evidence of retrieval quality.

For a platform whose thesis is *grounded answers over ungrounded ones*, a self-evaluation that is itself ungrounded is the sharpest available irony — and it is the number a stakeholder is most likely to quote.

**Fix.** Drive the real retriever; keep the golden set in `eval/golden.yaml` with question → expected sources; assert a minimum precision/recall and exit non-zero below threshold so CI can gate on it.

### P2-8 — There are no embeddings anywhere in the system

`docs/INGESTION.md` describes the flow as `... -> chunk -> embed/index -> ...` and the platform is described throughout as RAG. No embedding model is called anywhere; `ingestion/schema.py` declares no vector field; `app/rag/azure_backend.py` uses `query_type="semantic"`, which is Azure's re-ranker over keyword search, not vector retrieval. `ingestion/index.py:InMemoryIndex.search()` is substring matching.

This is a legitimate architectural choice — semantic ranking over BM25 is often competitive and much cheaper — but it is not what the documents say, and it caps recall on the paraphrase-heavy queries ("how does our auth middleware handle JWTs") that motivate the system. Either add a vector field plus an embedding batcher, or correct the flow diagram and say plainly that retrieval is lexical + semantic re-rank today.

### P2-9 — No model gateway seam, no cost metering, no rate limiting

`AzureRagBackend` constructs an `AzureOpenAI` client directly and calls `chat.completions.create` inline. There is no gateway abstraction, no per-team/per-agent quota, no token accounting, no cost telemetry, no timeout, and no retry policy on the inference call.

This is the one place where the implementation diverges from the build-vs-buy position it argues for: routing through an enterprise model gateway is precisely what makes provider substitution, per-team metering, and cost anomaly detection possible. `docs/PRODUCTION-READINESS.md` Gate 5 mandates measured unit costs, per-agent budgets, and a cost anomaly alert; none of the three has an implementation hook. The threat model's "model/token abuse causing cost or availability impact" has no control behind it.

**Fix.** Introduce a `ModelGateway` protocol with `complete(messages, *, budget, caller) -> Completion`; put timeout, retry, token accounting and per-caller quota in the one implementation; emit tokens/cost as span attributes alongside the existing `eip.query` span.

### P2-10 — Retrieved content is concatenated into the prompt with no injection defenses

`AzureRagBackend.synthesize()` builds `SOURCE: {path}\n{content}` blocks and places them in a user message. Prompt injection through retrieved code, tickets, or documentation is threat #1 in `governance/security-threat-model.md` and Gate 2 of the certification checklist, and the mitigation listed is "treat retrieved content as data, never as trusted instructions" — but nothing in the code marks the boundary, strips instruction-shaped content, or constrains the output.

This matters more here than in a general chatbot: the same retrieved corpus feeds agents that propose remediation runbooks. An attacker who can land a comment in an indexed repository is one hop from influencing a remediation proposal.

**Fix.** Delimit evidence with unspoofable markers, restate in the system prompt that evidence is data, validate that any proposed runbook name is in the allow-list *after* generation (never trust the model's choice), and add the poisoned-context tests Gate 2 already requires.

### P2-11 — `src/` is advertised scaffolding that returns nothing

`src/orchestrator/rag_orchestrator.py:retrieve()` returns `[]`. `src/agents/pr_guardian_agent.py:review()` returns `[]`. `src/agents/remediation_agent.py:propose()` returns `None`; `verify()` returns `False`. The README lists these under the repository map as "RAG orchestrator and agent components", and `app/` independently reimplements the same concepts.

`PRGuardianAgent.should_block()` is the sharp edge: it reads as a merge guardrail, and because `review()` always returns an empty list, it always returns `False`. A stub that returns "safe" is worse than no stub.

**Fix.** Delete `src/` (its concepts live in `app/`), or implement it and remove the duplication in `app/`. If it stays as scaffolding, mark it explicitly — `NotImplementedError` rather than an empty-but-plausible return.

### P2-12 — Deployment and infrastructure do not match the stated security posture

- `Dockerfile` copies only `app/`. The `ingestion/` package is absent from the image, so the ingestion worker cannot run in the deployed artifact.
- The container runs as root: no `USER` directive, no non-root UID.
- `helm/eip/templates/deployment.yaml` sets no `securityContext` (no `runAsNonRoot`, `readOnlyRootFilesystem`, or dropped capabilities), no `ServiceAccount`, no `NetworkPolicy`, no `PodDisruptionBudget`.
- `infra/terraform/main.tf` provisions `azurerm_search_service` and AKS with default public network access, no Private Endpoints, no Key Vault, and no `azurerm_role_assignment` for the Managed Identity the application expects. `architecture/azure-devops-self-healing-reference.md` lists "Private Endpoints and VNet integration" and "Key Vault" as reference components.

For a platform whose premise is that proprietary code never leaves a controlled boundary, a publicly reachable search service holding the entire indexed corpus is the gap most likely to be raised in a security review.

### P3-13 — README has drifted from the tree

- The repository map omits `ingestion/` entirely — PR #13 shipped a new top-level package without updating it.
- `.github/workflows/` is described as "CI, deck build and **PR intelligence** workflows". Only `ci.yml` and `build-board-deck.yml` exist; there is no PR intelligence workflow. This is the flagship Phase-3 capability, described as if shipped.
- The Azure-mode index contract (`source`, `content`, `repo`, `acl_groups`) contradicts `ingestion/schema.py` — see P1-4.
- The Quick Start's `pytest -q` and `python demo/aks/scenario_runner.py` both fail on a clean checkout — see P0-1.

### P3-14 — Smaller correctness and hygiene items

- `ingestion/chunkers.py:PythonASTChunker` chunks only top-level `FunctionDef`/`AsyncFunctionDef`/`ClassDef` nodes. If a file contains at least one such node, **all module-level code is dropped** — imports, constants, configuration dicts, `if __name__` blocks. A settings module with a single helper function loses everything else. The text fallback only triggers when there are *no* definitions at all. Emit a module-preamble chunk for the residue.
- `ingestion/chunkers.py:5` imports `replace` from `dataclasses`, unused.
- `app/rag/azure_backend.py:5` imports `Any`, unused.
- `IngestionPipeline.processed_events` is unbounded in-memory state — both a restart-correctness bug and a slow leak (see P0-2 for the fix that already exists in-tree).
- `.github/workflows/ci.yml` still triggers on `portfolio-reference-implementation` and `milestone-2-vertical-slice`, both merged and stale.

---

## 3. What the repository gets right

Worth stating explicitly, because the finding list above is unbalanced by construction:

- **The control model is correct and rare.** Separating "AI proposes" from "policy authorizes" from "allow-listed automation executes" — with mandatory verification and escalation-on-failure rather than retry-forever — is the invariant most self-healing efforts get wrong. `app/agents/control_loop.py` encodes it as an explicit state machine with an unconditional production approval gate, and the escalation paths are covered by intent-level tests.
- **Retrieval-before-model ordering is right.** Security trimming happens in the search layer, not by post-filtering model output. That ordering is very hard to retrofit; having it from the start is the most valuable structural decision here.
- **The autonomy tiers and certification gates are usable as written.** Tier 0-5 in the threat model and Gates 1-5 in `docs/PRODUCTION-READINESS.md` are specific enough to hold a promotion review against — including the point that L4 approval is action-specific rather than a blanket grant to an agent.
- **Build-vs-buy is called correctly.** Managed Identity to Azure OpenAI, no self-hosted foundation models, RAG plane and agents built in-house. The only gap is the missing gateway seam (P2-9).
- **The ingestion domain model (Generation B) is well-designed.** Content-hash chunk IDs, commit-excluded document identity so re-ingestion replaces stale chunks, and delete reconciliation are the three things naive ingestion pipelines omit. All three are present and correct.

---

## 4. Prioritized remediation plan

**P0 — restore the verification loop (about one day).** These are prerequisites; nothing else can be trusted until they land.

1. Add root `pyproject.toml` with `pythonpath = ["."]`; run the scenario runner as a module. CI goes green or tells the truth about why it is not. *(P0-1)*
2. Reconcile `ingestion/` onto Generation B; port the ledger, worker and file loaders; rewrite the two dead test modules. *(P0-2)*
3. Replace header-asserted identity with Entra token validation; fail closed; add a test that an unauthenticated caller retrieves nothing. *(P0-3)*

**P1 — make the documented controls real (about one week).**

4. Unify the index schema across writer, reader and README. *(P1-4)*
5. One ACL predicate, one conformance suite, both backends. *(P1-5)*
6. OPA becomes the single source of truth for runbooks; `opa test` runs in CI; the control loop calls it. *(P1-6)*
7. Eval harness drives the real retriever against a golden set and gates CI on a threshold. *(P1-7)*

**P2 — close the Phase 2/3 gaps (two to four weeks).**

8. `ModelGateway` seam with timeout, retry, token accounting and per-caller quota; cost on spans. *(P2-9)*
9. Prompt-injection boundary plus post-generation runbook allow-list validation; poisoned-context tests. *(P2-10)*
10. Decide on embeddings — implement a vector field and batcher, or correct the docs. *(P2-8)*
11. Delete or implement `src/`. *(P2-11)*
12. Non-root container including `ingestion/`; pod `securityContext`; Private Endpoints, Key Vault and Managed Identity role assignments in Terraform. *(P2-12)*

**P3 — restore documentation accuracy (half a day, do it alongside P0).**

13. README repository map, workflow list, index contract, Quick Start commands. *(P3-13)*
14. Chunker module-preamble residue; dead imports; stale CI branch triggers. *(P3-14)*

**Then, the flagship Phase 3 capability that is currently claimed but absent:** a PR intelligence workflow. The pieces largely exist — `PRGuardianAgent`, the retrieval plane, the policy engine. Wiring an on-`pull_request` workflow that retrieves related internal context for a diff and posts a non-blocking review is the most visible demonstration of the whole thesis, and the README already promises it.

---

## 5. Method and scope

Reviewed by reading the implementation surface on `main` @ `faa1ba4` — `app/`, `ingestion/`, `src/`, `tests/`, `eval/`, `demo/`, `infra/`, `helm/`, the `Dockerfile`, both workflows, and the architecture, governance, ingestion and production-readiness documents — plus the CI run history via the GitHub API.

**Scope limitation.** This pass did *not* read the program documents that define the objective: `docs/executive-memo.md`, `docs/board-deck-narrative.md`, `docs/kpi-system.md`, `finops/cfo-roi-model.md` and `roadmap/technical-roadmap-24-months.md`. The findings below are therefore graded against a production-platform bar rather than against this program's own phase exits and investment gates. Several items — Entra identity, private networking, embeddings, cost-per-query telemetry — are scheduled roadmap work in Phase 0-1, not defects, and should be re-graded on that basis. The `pytest` collection failure (P0-1) was reproduced locally: `pytest -q` fails identically to CI, while `python -m pytest -q` passes six tests — which is what makes the break invisible to a developer following the README. Import failures in P0-2 were verified by reading the defining and importing modules directly; the two dead test modules were read in full. Terraform, Helm and container findings are from static reading — `terraform validate`, `helm lint`, `opa test` and `docker build` were not executed in this pass.

No source, configuration, workflow, or infrastructure file was modified by this review. This document is the only addition.
