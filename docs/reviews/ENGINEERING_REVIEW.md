# Engineering Review — Company Brain

| | |
|---|---|
| **Review type** | Architecture, codebase, and product-maturity review |
| **Baseline reviewed** | origin/main at fc3b885 (2026-08-27) |
| **Review date** | 2026-08-28 |
| **Reviews recorded** | Consolidated team review (sections 1–6, sequenced plan); independent second review (the *Independent review* section and score column) |
| **Product truth** | Company Brain is the product; PR Guardian is its first, deliberately narrow, non-blocking wedge. |
| **Evidence rule** | Repository code and CI demonstrate reference behavior. They do not demonstrate a deployed pilot, production readiness, or autonomy certification. |

## Executive verdict

The repository has a strong **reference architecture** for a Company Brain: it turns company
knowledge and operational signals into evidence-backed decisions, and keeps any consequential
action behind deterministic policy, approvals, and bounded executors. Its most mature qualities
are the safety model, domain vocabulary, explicit reference-versus-evidence documentation, and
end-to-end CI. The successful [Reference Implementation CI run](https://github.com/hatan4ik/engineering-intelligence-platform/actions/runs/33060362720)
validates the baseline revision.

This is not yet a high-maturity product. It has no named pilot repository, retained operational
evidence, deployed Temporal business workflow, or certified remediation scope. The code also
needs a focused round of Python type-boundary, module-boundary, and packaging cleanup before
new product surfaces are added. Those are normal and tractable next steps, not a reason to
broaden the architecture or claim a premature platform completion.

### Scorecard

Scores describe design and repository quality at the reviewed revision, **not** production
readiness. A score of 8 for safety architecture cannot substitute for the evidence required by
the [production-evidence registry](../PRODUCTION-EVIDENCE.md).

| Dimension | Score | Independent review | Assessment |
|---|---:|---:|---|
| Product architecture | 8 / 10 | 8 / 10 | Clear Company Brain north star, five-plane model, and a sensible initial wedge. |
| SOLID design | 7 / 10 | 7 / 10 | Strong ports/contracts and pure policy; a few orchestration modules own too many responsibilities. |
| Clean code | 7 / 10 | 6 / 10 | Good names and invariants, but large composition modules and ambient configuration make change harder than necessary. |
| Pragmatic delivery | 8 / 10 | 6 / 10 | Fail-closed defaults and full-image CI are excellent; manifest and documentation drift need closing. |
| Systems engineering | 8 / 10 | 6 / 10 | Safety boundaries are unusually explicit for a reference implementation; operational evidence and traceability are still missing. |
| Type-system thinking | 6 / 10 | 5 / 10 | Good immutable value objects and protocols, but Any/untyped payloads and missing static gates weaken the boundary. |
| Product maturity | 3 / 5 | 3 / 5 | Strong reference slices; no real pilot or retained outcome evidence. This is consistent with the repository maturity scale, where 3 means reference implementation and 5 means production-proven. |

The **Independent review** column is from the second, separately conducted review recorded in
the [Independent review](#independent-review-2026-08-28) section. Where the two columns differ,
that section names the specific evidence behind the lower score.

## Product alignment: this is a Company Brain

The product is not a collection of AI utilities. It is a governed organizational system that can:

1. **Remember** — ingest and retain authorized engineering and operational knowledge with
   provenance, lifecycle, and access controls.
2. **Model** — connect code, services, owners, infrastructure, decisions, deployments, and
   incidents into a company world model.
3. **Reason** — assemble authorized evidence, apply deterministic risk/policy, and make
   uncertainty visible instead of inventing certainty.
4. **Assist** — meet people in their work, starting with pull-request review, with explainable,
   useful recommendations.
5. **Act only when earned** — use approval, OPA, allow-listed runbooks, independent verification,
   rollback, and retained evidence to grow autonomy per service, environment, and runbook.

That interpretation matches the [system design](../../architecture/design.md),
[capability reconciliation](../../architecture/CAPABILITY-RECONCILIATION.md), and
[product strategy](../PRODUCT-STRATEGY.md). The product strategy correctly narrows the immediate
job to **PR Guardian for one or two repositories in shadow mode**. Incident intelligence and
remediation remain architectural investment/reference paths until PR Guardian has demonstrated
usefulness, safety, and a feedback loop with real users.

## Reconciliation of the parallel review

The original review had several important strengths. They are retained below, with corrections
where claims went beyond the checked-in baseline.

| Parallel-review observation | Review conclusion | Evidence-based correction or addition |
|---|---|---|
| Protocols, immutable domain objects, and pure policy demonstrate sound SOLID instincts. | **Agree.** | These are good foundations for a Python system with TypeScript-style contracts. Keep them as the default at domain boundaries. |
| The digital twin, fail-closed security, and OTel spans show systems thinking. | **Agree, with scope.** | The reference code and design have these controls; neither proves a real AKS/production exercise. app/main.py does create PR Guardian spans and sets repository/risk attributes. |
| Temporal provides a fully durable remediation/control plane that resumes business workflows. | **Not supported by main.** | The [Temporal worker boundary](../TEMPORAL-WORKER-RUNBOOK.md) expressly registers only a non-consequential evidence workflow. It is undeployed and has no business state, audit export, or mutation authority. |
| A KubernetesClientAdapter substitutes for the subprocess runner. | **Not supported by main.** | Main uses KubernetesActionAdapter with a narrow CommandRunner port and argv-only kubectl calls. A separate client adapter was not part of the reviewed main baseline. |
| Terraform uses Helm to deploy the workload. | **Not supported by main.** | infra/terraform/main.tf declares only the AzureRM and Random providers. Helm chart validation occurs in CI, but Terraform does not own Helm/Kubernetes deployment. |
| The code has a total absence of Any. | **Not supported by main.** | The reviewed Python implementation has 45 Any occurrences, 41 direct environment reads, and 24 casts/type-ignore markers in product packages. This is a manageable type-boundary backlog, not a condemnation. |
| State is PostgreSQL/Temporal. | **Overstated.** | The present repository contains reference state/audit adapters and an explicitly bounded Temporal path. The production-evidence registry confirms that no environment or production evidence is recorded. |
| The whole platform is already FAANG-tier. | **Refine.** | Several architectural choices are high quality. Overall maturity should be described as a strong, CI-validated reference implementation with explicit gaps, not as a completed production platform. |
| No new major subsystem should be added before PR Guardian has pilot outcome data. | **Agree, with a safety exception.** | Freeze new product-surface expansion until the shadow pilot yields retained outcomes. Safety defects, operating maintenance, and the focused architecture-quality refactoring wave remain in scope. |

## What is strong and should be preserved

### System safety and trust boundaries

The design has the right foundational rule: models may reason and propose, while identity/ACLs
constrain evidence, deterministic policy authorizes change, bounded adapters execute, and an
independent signal verifies outcome. This is the right architecture for a Company Brain; it
separates helpful intelligence from authority.

Keep and extend these patterns:

- Authorization before retrieval and evidence/provenance carried with a result.
- Fail-closed configuration, secrets, webhook validation, and incomplete deployment defaults.
- Explicit autonomy progression from L0 to L4 by runbook/service/environment, rather than
  promoting an agent wholesale.
- Plan-bound human approval, OPA policy, fixed runbook catalogues, rollback, kill switches, and
  an isolated digital-twin concept.
- The full-image import-closure check, SBOM output, Terraform/Helm linting, OPA tests, evaluation
  harness, and container smoke test in the CI workflow.

### Domain vocabulary and deterministic core

RiskAssessment, policy decisions, workflow records, audit concepts, and control-plane contracts
use intention-revealing terms rather than generic Manager/Handler abstractions. Frozen data
classes, tuples, mappings, and Protocol ports are good Python equivalents of readonly TypeScript
models and interfaces. Deterministic risk/policy functions are practical to test and auditable
enough for future enforcement decisions.

### Product discipline already documented

The repository distinguishes reference implementation from operational proof in
[Current Position](../CURRENT-POSITION.md), [Capability Reconciliation](../../architecture/CAPABILITY-RECONCILIATION.md),
and [Production Evidence](../PRODUCTION-EVIDENCE.md). This distinction is unusually valuable and
should stay non-negotiable as delivery accelerates.

## Findings and recommendations

### 1. SOLID: retain ports, reduce orchestration ownership

**What works.** The code uses narrow contracts such as the command-runner and evidence-provider
ports. KubernetesActionAdapter accepts the runner rather than constructing a shell boundary, and
deterministic intelligence remains separated from external GitHub/Temporal/Kubernetes calls. This
is solid dependency inversion.

**Finding.** product/pr_guardian_service.py has one public evaluate() method that coordinates
roughly ten concerns: validation, change classification, context retrieval, risk calculation,
policy, finding construction, workflow/audit persistence, and publication outcome. Likewise,
app/operations_api.py contains DTO normalization, provider construction, GitHub publication,
secret validation, FastAPI routes, and response serialization. These functions are understandable
today but will become fragile as more Company Brain products consume them.

**Recommendation.** Keep public application services small and introduce cohesive internal stages
rather than microservices:

    PR event
      -> DiffCollector / ChangeClassifier
      -> ContextResolver
      -> RiskEvaluator (pure)
      -> PolicyEvaluator (pure)
      -> FindingFactory
      -> WorkflowRecorder / OutcomeRecorder
      -> ReviewPublisher
      -> TelemetryRecorder

PRGuardianService should compose those dependencies and own the use case, not each mechanism.
For operations, split app/operations_api.py into request DTOs, evidence/provider factory, analysis
presenter, publisher adapters, and thin route wiring. This makes a second surface, such as incident
intelligence, reuse the core finding/evidence/outcome contracts instead of copying PR-specific logic.

### 2. Clean code: make composition and configuration explicit

**What works.** Naming is generally clear and safety conditions are near the code that enforces
them. The use of argv rather than shell interpolation in the Kubernetes adapter is an especially
good example of making unsafe behavior difficult to express.

**Finding.** Several modules are now large enough to blur their reason to change:

| Module | Approximate size | Main concern currently mixed in |
|---|---:|---|
| company_brain/store.py | 46 KB | persistence, query behaviour, and lifecycle support |
| company_brain/memory.py | 27 KB | memory modelling and access/use behaviour |
| app/operations_api.py | 23 KB | HTTP, configuration, providers, publishing, and serialization |
| company_brain/world_model.py | 21 KB | graph/world-model concerns |
| product/pr_guardian_service.py | 16 KB | end-to-end product orchestration |

Size alone is not a defect. The indicator is mixed policy, transport, serialization, and
composition in the same file. Extract by responsibility only when a new component has a clear
owner and tested contract; avoid a cosmetic file split.

**Finding.** Configuration is ambient. The source tree contains 41 direct os.getenv or os.environ
reads across the reviewed packages. This makes a capability's required inputs, safe defaults, and
test configuration harder to see at its boundary.

**Recommendation.** Introduce a typed immutable settings object per deployed process, validate it
at startup, and pass capability-specific configuration to factories. Tests should construct
settings explicitly. Read environment variables at the composition root only. This is the Python
analogue of parsing process.env once into a typed TypeScript configuration object.

**Finding.** app/main.py remains an overly broad composition root. It currently carries FastAPI
composition, public request models, deterministic demo retrieval, identity resolution, GitHub
webhook handling, feedback paths, query behavior, and Azure-backend selection. This makes startup
and route behavior harder to reason about in isolation.

**Recommendation.** Evolve the entrypoint toward a small create_app(settings) function that wires
already-tested routers and capability factories. Move demo-only retrieval and integration-specific
wiring behind explicit adapters. The objective is not an abstract framework; it is a boring,
inspectable entrypoint that makes the deployed capability set obvious.

### 3. Pragmatic delivery: make one source of packaging truth

**What works.** The CI pipeline checks more than unit tests: docs, evaluations, an image build,
full import closure, Terraform/Helm syntax, OPA, SBOM generation, and a smoke test. This is
excellent pragmatic risk reduction.

**Finding.** Python packaging declarations are not the same set as the release image. The
Dockerfile and app.import_closure.SHIPPED_PACKAGES include company_brain, topology, remediation,
and resilience, while the pyproject.toml package-discovery list omits them. The image test catches
runtime imports, but build/distribution metadata can drift and give library or tooling consumers
an incomplete package.

**Recommendation (P0).** Define one canonical package inventory and test equality across:

1. pyproject.toml package discovery;
2. Dockerfile first-party COPY inputs; and
3. app.import_closure.SHIPPED_PACKAGES.

Prefer generating one of the latter lists from a small reviewed manifest rather than maintaining
three hand-edited inventories. The check should fail with a readable set difference.

**Finding.** Documentation state has drifted. CURRENT-POSITION.md says Reference CI is open
because 13 tests fail, while the reviewed main revision has a successful Reference Implementation
CI run. The failing PR Guardian shadow-publisher workflow runs (four on 2026-08-27; see the
[Independent review](#two-factual-corrections-to-the-text-above) for the cause) are not the same
workflow and should be diagnosed independently rather than used to report main CI as failed.

**Recommendation (P0).** Correct the Current Position row in the PR that establishes its
verified replacement status. Its update rule is right: never update the reviewed date without
rechecking every stated row.

### 4. Systems engineering: turn architecture claims into traceable evidence

**What works.** The architecture anticipates the hazards most AI platforms hand-wave: ACL leakage,
unsupported high-severity advice, policy outage, audit outage, unsafe mutation, recovery, and
blast radius. The digital-twin and L3/L4 conditions are a sound safety model for later use.

**Finding.** The platform has architecture decision records, capability status, and a production
evidence contract, but lacks a single machine-checkable **requirements-to-evidence matrix**. A
reviewer should be able to start from a requirement such as ACL is enforced before retrieval and
discover its design decision, implementation package, automated test, evidence artifact, owner,
expiry, and risk acceptance.

**Recommendation.** Add an authoritative, versioned requirements baseline in YAML or JSON with
at least these fields:

    id: EIP-SEC-014
    statement: Retrieval is authorized before any evidence reaches model context.
    criticality: high
    implemented_by: [ingestion/access_control.py]
    verified_by: [tests/test_authorized_retrieval.py]
    operational_evidence: required_for pilot/advisory/enforcement
    owner: platform-security
    review_cycle: 90d

CI should validate referenced paths and tests, while a generated Markdown view links it into
design/review documentation. Do not manufacture operational evidence from CI; the matrix should
make the absence explicit.

**Finding.** The only in-scope Temporal worker is an undeployed evidence-worker boundary. The
broader durability, backup/restore, independent verification, and runbook certification claims
remain future work. This is properly documented, but reviewers need it visible in all readiness
material so target-state diagrams cannot be misread as running systems.

**Recommendation.** Add a compact implemented/reference/operationally-proven status line to every
architecture diagram and high-level product page. Treat operational SLOs, latency/cost
distributions, recovery drills, and evidence retention as promotion gates, not post-launch work.

### 5. Type-system thinking: make untrusted data narrow and explicit

**What works.** Frozen domain objects, tuple/mapping choices, typed Protocols, and Pydantic at
some API boundaries are a good Python equivalent of strict TypeScript. They make business rules
legible and prevent accidental mutation in core paths.

**Finding.** Any occurs 45 times in the reviewed product packages. Some are justified at the
untrusted edges, such as webhooks, Azure payloads, and JSON, but several flow through
helper/factory and reporting paths. The repository currently has no visible static type-checking
gate.

**Recommendation.** Do not attempt a repo-wide Any ban. Instead:

- Parse external JSON immediately into Pydantic request/event DTOs or TypedDict structures.
- Keep Mapping[str, object] at dynamic boundaries and narrow with small normalizers.
- Make public service and adapter interfaces fully typed; prohibit Any in newly touched domain and
  policy modules except with a local justification.
- Add Ruff and Pyright gradually: start with company_brain, intelligence, product, and remediation
  public APIs; make the baseline ratchet down rather than blocking unrelated code.
- Use discriminated result types for expected states, such as insufficient_evidence, denied,
  proposal, and executed, instead of dictionary response shapes wherever the result crosses a
  product boundary.

For example, operations routes should return an explicit IncidentReport response model with typed
status, autonomy level, correlation/workflow IDs, service/environment, impacted services,
analysis, and proposals. It should make executed false structurally true for the L2 proposal path,
rather than relying on hand-assembled dictionary keys at serialization time.

This will improve the quality of agent-written and human-written change alike: the type system
becomes a design constraint, not a cleanup chore.

### 6. Product maturity: build trust before surface area

**What works.** The PR Guardian strategy gives the correct operating model: shadow first,
non-blocking, repository-specific thresholds, explainable evidence, feedback capture, and a kill
switch. It also prevents a PR Guardian pilot from accidentally conferring authority on
incident/remediation workflows.

**Finding.** The next Company Brain proof is not another architecture component. It is a measured
human-feedback loop: did reviewers find the recommendation correct, useful, and actionable, and
did it prevent a meaningful miss without creating noise? No named pilot repository or retained
observation record exists at this baseline.

**Recommendation.** Make the next product increment a shadow-pilot package, with a named owner
and a documented data classification, including:

1. installation and safe non-blocking configuration;
2. per-finding reviewer disposition: accepted, rejected, ignored, or insufficient evidence;
3. post-merge outcome correlation reviewed as a signal, not blindly labelled ground truth;
4. weekly precision, observed false-negative, citation-quality, latency, cost, and opt-out review;
5. a documented pause/kill procedure and service-owner escalation path; and
6. an immutable evidence record for every promotion decision.

Adopt the following portfolio gate: **do not build a new major Company Brain product subsystem
until PR Guardian produces retained shadow-pilot quality and value data.** This does not block
security remediation, documentation correction, maintenance, or the refactoring items below. It
does prevent architecture ambition from outrunning demonstrated user value.

Only after shadow results meet pre-agreed thresholds should the product offer a non-blocking
advisory check. Enforcement must remain a separate, narrow decision for one deterministic,
calibrated rule with waiver, expiry, and rollback. Incident intelligence should begin only after
PR Guardian demonstrates that its shared evidence/finding/outcome contracts work with people.

## Independent review (2026-08-28)

A second review was run separately against the same baseline (`origin/main` at `fc3b885`) by
four independent reviewers, one per lens — SOLID/Clean Code, Pragmatic Programmer, systems
engineering, and type-system thinking — with file:line citations required for every finding, and
the sharpest claims re-verified by hand. Its full report is published separately; this section
records only what it adds to, corrects in, or weighs differently from the review above. Test
suite at the reviewed revision: 656 passed, 1 skipped.

### Agreement

The two reviews reach the same diagnosis on every point in the *Findings and recommendations*
section: `evaluate()` and `app/operations_api.py` own too many concerns; configuration is
ambient; the packaging inventory has drifted from the release image; `CURRENT-POSITION.md:31` is
stale; there is no static type gate; product maturity is 3/5 on the repository scale because no
pilot or retained evidence exists. The corrections of the parallel review in the reconciliation table are all
confirmed against the baseline: the Temporal worker is evidence-only, no `KubernetesClientAdapter`
exists, `infra/terraform/main.tf` declares only the `azurerm` and `random` providers, and `Any`
is present (64 occurrences across all non-test Python; 20 in `product/`, `company_brain/`,
`intelligence/`, `app/`). The Reference Implementation CI run cited above (33060362720) is
confirmed successful at `fc3b885`.

### Two factual corrections to the text above

1. **Shadow-publisher failures.** There are four failing `PR Guardian Shadow Publisher` runs on
   `main` on 2026-08-27, not two (33060203139, 33060276413, 33060515807, 33061041162). All four
   fail at the same step, `actions/download-artifact`, because the triggering evaluate run produced
   no observation artifact. The fail-soft "untrusted or missing artifact" path added in the
   Stage 3 work exists in `scripts/publish_pr_guardian_shadow.py`, but it runs *after* the
   download step, so it is never reached. The fix is a `continue-on-error` (or an artifact-presence
   condition) on the download step so the script's own missing-artifact branch handles the case.
2. **Counts.** The figures "45 Any, 41 environment reads, 24 casts/type-ignore markers" do not
   reproduce at any package scope tried. Measured at the baseline: all non-test Python (171
   files) — 64 `Any`, 53 `os.getenv`/`os.environ.get` reads, 28 `# type: ignore`, 0 `cast()`;
   product packages only (`product`, `company_brain`, `intelligence`, `app`) — 20 / 19 / 1 / 0.
   The order of magnitude and the conclusion are unchanged; the review should state its scope.

### Findings the scorecard above does not account for

These are the reasons the *Independent review* column scores Pragmatic delivery and Systems
engineering at 6 rather than 8. Each is a single, verifiable fact at the baseline.

| # | Finding | Evidence | Why it outweighs a scorecard point |
|---|---|---|---|
| I-1 | **Both kill switches are unsettable in the deployed chart.** `EIP_AUTONOMY_KILL_SWITCH` and `EIP_PR_GUARDIAN_KILL_SWITCH` are implemented, tested, and correctly ordered ahead of every other check — and appear nowhere under `helm/`. `/healthz` does not report their state. | `remediation/executor.py:30-48,244-254`; `product/pr_guardian/enforcement.py:31,126-129`; `grep KILL_SWITCH helm/` → 0 matches; `app/runtime_wiring.py:34-40` | The emergency stop exists on paper only in the topology the chart deploys. |
| I-2 | **The deterministic policy boundary is optional by default.** `EIP_REQUIRE_OPA` defaults to `"false"`, so a deployment that forgets the flag silently authorizes through the in-process reference evaluator. The variable is undocumented. | `remediation/executor.py:261` | Contradicts the "deterministic policy is the sole authority" guardrail stated in this document. |
| I-3 | **`EIP_BACKEND` is normalised three different ways.** `.strip().lower()` in `app/auth_mode.py:24` and `app/runtime_wiring.py:35`; compared raw at `app/main.py:271`. `EIP_BACKEND=Azure` therefore refuses header identity, reports `azure` in `/healthz`, and still serves the deterministic demo corpus. | `app/auth_mode.py:24`; `app/runtime_wiring.py:35`; `app/main.py:271` | A live auth/backend divergence caused by one piece of knowledge written three times. |
| I-4 | **The policy denial vocabulary and precedence exist three times by hand** — in the Rego bundle and in two Python modules — with no conformance test running both engines over one input corpus. The docstrings claim they "mirror" each other; nothing enforces it, and the pair drifted once (permissively) during the Stage 6 work. | `infra/policy/remediation-policy.rego:17`; `remediation/policy.py:36`; `remediation/opa_policy.py:68,95,264` | The authorization boundary is two hand-synced copies. |
| I-5 | **Correlation IDs are generated, not propagated.** Every `ControlPlaneWorkflows.start_*` mints a fresh `uuid4()`, so the HTTP `X-Correlation-Id` and the GitHub delivery ID never reach the audit event or telemetry. | `control_plane/workflows.py:47,95,145,185`; `app/main.py:225,258` | Breaks the NFR's own end-to-end traceability claim and this document's "require a correlation ID for every consequential transition" guardrail. |
| I-6 | **Twelve shipped packages have no `__init__.py`** (`app`, `feedback`, `finops`, `integrations`, `intelligence`, `orchestration`, `portal`, `product`, `security`, `topology`, `remediation`, `resilience`). Consequences: `pyproject.toml`'s `packages.find` ships nothing for them, and `mypy` aborts with "Source file found twice" before checking anything. | `ls */__init__.py`; `pyproject.toml` `[tool.setuptools.packages.find]` | Makes P0.2 (package truth) and P1.1 (type baseline) impossible until fixed; it is the first line of both. |
| I-7 | **Terraform provisions none of the durable-path elements the code assumes.** No Cosmos, Service Bus, Temporal server, diagnostic settings, or alerts, while ~20 `EIP_COSMOS_*` / `EIP_TEMPORAL_*` variables and `state/cosmos_store.py` presume them. The deployed chart supplies 5 of ~75 `EIP_*` variables. | `infra/terraform/main.tf`; `helm/eip/templates/deployment.yaml:59-81` | The design and the infrastructure describe different systems; docs should say "reference-only" until IaC exists. |
| I-8 | **Type-boundary specifics.** `ProductMode` is downcast to `str` at `product/pr_guardian_service.py:102` and then compared against `.value` at `:346`; `validate_observation` returns `dict[str, object]`, billed as four `# type: ignore` in six lines at `scripts/publish_pr_guardian_shadow.py:157-162`; zero `NewType`, zero `assert_never`, one `Literal` in the repository; `control_plane/remediation.py:94` maps any unknown status string to `FAILED` silently. With `--explicit-package-bases`, mypy reports 39 errors (49 strict) on `product remediation state`, 8 of them stale `# type: ignore` comments written for a checker nobody ran. | as cited | Concrete targets for P1.1; the annotation coverage (97.9%) means the expensive part is already paid for. |
| I-9 | **Broken windows.** Three one-shot documentation-migration scripts remain tracked at the repository root (`rewrite_links.py`, `fix_design_target_state.py`, `fix_temporal_alignment.py`); `ci.yml` floats `@v4`/`@v3` action tags while every other workflow pins SHAs; `pyproject.toml` says `0.6.0` and `helm/eip/Chart.yaml` says `0.2.0`; `README.md`'s repository map omits seven top-level packages including `company_brain/`. | repository root; `.github/workflows/ci.yml:14,18,26,30`; `helm/eip/Chart.yaml:4` | Cheap to close, and they set the standard newcomers copy. |
| I-10 | **Scope versus wedge.** `PRODUCT-STRATEGY.md:50` explicitly defers L3 remediation, L4 autonomy, and incident automation. `company_brain/` (3.1k LOC), `orchestration/` (1.8k), `remediation/` + `resilience/` (1.9k) serve that deferred scope — roughly a third of production Python. 39 modules are importable only from tests. | package line counts at the baseline | Not a defect in the code; a maintenance cost carried without product evidence, and the source of this month's merge collisions. |

One note in the other direction: mypy's `operator` complaint at `state/cosmos_store.py:68`
(`None + int`) is a narrowing false-positive, not a live bug — the `None` case is guarded by
`1 if current is None else current_version + 1`.

### Additions to the sequenced plan

The plan below is right in shape. The independent review adds one slice ahead of P0.1, one
alongside P1.2, and sharpens P0.2 and P1.1. The rows are also inserted into the plan table so
there is one sequence, not two.

| Priority | Outcome | Deliverable and acceptance condition |
|---|---|---|
| **P0.0** | Operable safety controls | Both kill switches in the Helm env block from a ConfigMap read per request; `EIP_REQUIRE_OPA` default inverted (or the executor fails closed whenever `EIP_CONTROL_PLANE_MODE != reference`); `EIP_BACKEND` normalised once in `app/auth_mode.py`; kill-switch state, control-plane mode, and image digest reported by `/healthz`. Acceptance: a deployed pod can be stopped without a redeploy, and `/healthz` shows it. |
| **P0.2 (sharpened)** | Package truth | Starts by adding the twelve missing `__init__.py` files; without them `packages.find` ships nothing for those packages and no checker can run. |
| **P1.1 (sharpened)** | Type baseline | `[tool.mypy]` + `[tool.ruff]` with today's 39 errors as the ceiling; thread the request/delivery correlation ID through `ControlPlaneWorkflows.start_*` with a contract test. |
| **P1.2b** | Policy conformance | One input corpus evaluated by both the Rego bundle (`opa eval`) and `LocalReferenceEvaluator`, asserting identical verdict and reason for every case. Acceptance: the test fails on any one-sided edit to either engine. |

### Guardrail on how reviews are reconciled

Correct the review, not the code, when a review's claim is untrue at the baseline. During this
consolidation, uncommitted scripts appeared in the working tree that would retroactively make two
of the parallel review's unsupported claims true — re-adding a stub Temporal workflow named
`eip.remediation.v1` (removed in PR #80 because it collides with the gated remediation workflow
and would report success with every gate skipped) and adding a Helm provider to Terraform. Neither
change is justified by a requirement; both would be justified only by the review text. They
should not be applied.

## Sequenced delivery plan

The aim is to reduce the riskiest uncertainty first while preserving the Company Brain direction.
Each numbered slice should be a small, independently reviewable pull request; do not combine a
refactor, a new product surface, and a deployment claim.

| Priority | Outcome | Deliverable and acceptance condition |
|---|---|---|
| **P0.0** | Operable safety controls | Kill switches settable in the deployed chart, `EIP_REQUIRE_OPA` fail-closed by default, `EIP_BACKEND` normalised once, `/healthz` reports mode and switch state (see the [Independent review](#additions-to-the-sequenced-plan)). |
| **P0.1** | Portfolio focus | Record the product-surface freeze: no major new subsystem before retained PR Guardian shadow-pilot outcomes; safety and maintenance work continue. |
| **P0.2** | Package truth | Canonical package inventory plus CI set-equality test for packaging metadata, image contents, and import closure. Starts by adding the twelve missing `__init__.py` files. |
| **P0.3** | Truthful current state | Update CURRENT-POSITION.md against verified current CI status; add a review-date/check reference. Diagnose shadow-publisher failures separately. |
| **P0.4** | Maintainable product core | Split PR Guardian into cohesive pipeline components, including telemetry recording, while holding existing behavioural tests and public contract constant. |
| **P0.5** | Maintainable operations entrypoint | Decompose operations_api.py into typed DTOs, factories, presenters, publishers, and thin routes; reduce app/main.py to explicit application composition. |
| **P1.1** | Type-boundary baseline | Typed process settings, external-event DTOs, explicit report responses, Ruff/Pyright baseline for core packages, and a non-increasing dynamic-typing budget. |
| **P1.2** | Engineering evidence traceability | Requirements-to-design-to-test baseline with CI link validation and an explicit operational-evidence field. |
| **P1.2b** | Policy conformance | One input corpus evaluated by both the Rego bundle and `LocalReferenceEvaluator`; identical verdict and reason asserted for every case. |
| **P2.1** | Company Brain contract | Extract shared Evidence, Finding, Outcome, and provenance contracts that PR Guardian and future operational products use without duplication. |
| **P2.2** | Shadow-pilot readiness | Pilot onboarding, disposition capture, weekly report, cost/latency metrics, exit/stop criteria, and evidence record format. No enforcement. |
| **P3** | Advisory evidence | Run and review the named shadow pilot; make the advisory decision from retained outcomes, not implementation confidence. |
| **P4** | Later autonomy research | After the product feedback loop is credible, certify one L2/L3 runbook through real scoped drills, then consider bounded L4 only per the existing evidence gates. |

### Architectural guardrails for every delivery slice

- Keep the Company Brain source of truth separate from product presentation surfaces.
- Keep LLM output advisory; deterministic policy is the sole authority for any action.
- Require a correlation ID, provenance, and evidence classification for every consequential
  finding or workflow transition.
- Treat every integration as a trust boundary: authenticate, authorize, validate schema, bound
  retries/cost, and define failure/rollback semantics.
- Prefer one well-tested shared contract over a cross-product framework or a generic utils bag.
- Do not mark any capability production-ready without a scoped, retained evidence record.

## Definition of progress

The Company Brain is progressing when the organization can show, for a narrow user workflow,
that it remembers authorized facts, forms a grounded and reviewable conclusion, produces a useful
human decision, and can measure the result. The correct progression is:

    Reference contracts and safety boundaries
      -> typed, testable product core
      -> shadow observations with human dispositions
      -> evidence-backed advisory
      -> certified, bounded operational proposals
      -> rehearsed and independently verified remediation
      -> per-runbook bounded autonomy

The immediate milestone is therefore not “finish the platform.” It is a trustworthy PR Guardian
shadow pilot that validates the Company Brain shared memory, evidence, reasoning, and feedback
loop. That creates the empirical foundation that later incident and remediation capabilities must
reuse.

## 7. Integration with the 22-Skill Operating Stack Audit

A parallel **Skill-Driven Documentation & Design Review** (`skill-driven-doc-review.md`) evaluated the repository against the Enterprise AI Transformation 22-Skill Operating Stack. That audit strongly corroborates the engineering conclusions in this document, identifying three critical cross-cutting themes:

1. **Implementation leads documentation:** The codebase enforces a stronger, more complete operating model than the documentation describes. For example, the code encodes typed phases, approval gates, and escalations, but the Target Operating Model (TOM) document lacks a role-evolution table and a formalized AI↔human handoff map. The governance documentation asserts remediation surfaces are the strictest, but fails to mathematically derive this from a data-sensitivity × decision-impact tiering.
2. **Missing Latency/Throughput Budgets:** The skill audit highlights a critical systems-engineering gap (Skill 09): there is no documented latency model for the self-healing chain (retrieve → LLM synthesize → policy → simulate → execute → verify). The implicit budget—a 60-second job lease—is mis-sized for a complete simulate+execute pass.
3. **The gate structure is production-grade; the evidence is not yet real:** Both reviews agree that the architectural boundaries (kill switches, Temporal durability, digital twin sandboxes) are robust. However, the evidence harnesses currently validate *shape* rather than *truth*. Advancing the product maturity requires producing real evidence artifacts (load tests, rehearsed-rollback logs with dates, finance sign-offs) rather than adding more gates.

### Consolidated Action Items from the Skill Audit
To align the engineering architecture with the enterprise operating model, the following operator handoffs must be executed:
- **Governance:** Derive and document the data-sensitivity × decision-impact tier for every workflow. Close the three identified audit-log gaps (confidence scores, RAG evidence lineage, and log-access policy).
- **Systems Engineering:** Publish a strict latency/throughput budget per workflow step and resize the execution lease accordingly. Wire the semantic embeddings into the production path.
- **Process:** Author a formalized Target Operating Model (TOM) section detailing role evolution (e.g., how SRE tasks shift from execution to validation) and Human-in-the-Loop SLAs. Obtain finance sign-off on the token-spend budget guardrails.
