# L4 Promotion Runbook

| | |
|---|---|
| **Classification** | Current implementation state |
| **Owner** | Platform Engineering + Security |
| **Status** | Gate implemented; no scope in this repository is certified and no certification record exists |
| **Scope** | How one service/environment/runbook scope is certified for L4, and what the execution path does without that certification |
| **Related** | [`../architecture/l4-certification.md`](../architecture/l4-certification.md), [`L3-REHEARSAL-RUNBOOK.md`](L3-REHEARSAL-RUNBOOK.md), [`PRODUCTION-EVIDENCE.md`](PRODUCTION-EVIDENCE.md), [`evidence/README.md`](evidence/README.md) |

L4 is not a platform mode and not a model capability. It is a property of one
`service + environment + runbook + blast-radius budget` scope, and it lapses.

## The promotion chain

From `architecture/l4-certification.md`:

```
L3 production approval
  -> repeated supervised exercises
  -> certification evidence
  -> L4 for one service/runbook scope
```

Each arrow is a human decision with an artifact behind it. Nothing in this
repository advances the chain on its own.

1. **L3 production approval.** A reviewed `ServiceAutonomy` entry grants the
   scope L3. Every L3 execution still requires a verified human approval.
2. **Repeated supervised exercises.** `scripts/run_l3_exercises.py --runner
   kubectl` runs the suite against a real cluster. Exercises execute *at L3* —
   they are the supervised runs the promotion rule names, so they do not
   themselves require the certification they exist to earn. `--runner simulated`
   is a rehearsal: it writes `"evidence_grade": "rehearsal"` and the certifier
   discards it.
3. **Certification evidence.** The nine mandatory items below, retained.
4. **L4 for one scope.** `scripts/certify_l4_scope.py` writes one
   `l4-certification-<scope-hash>.json`. That file is the only thing
   `remediation.executor.execute_control_loop` accepts as authority for an L4
   mutation.

## The nine mandatory items

`resilience.certification.MANDATORY_L4_EVIDENCE`, in the order
`architecture/l4-certification.md` lists them:

| Item | Where it comes from |
|---|---|
| `rollback-exercised` | a passing `rollback` exercise |
| `kill-switch-exercised` | a passing `kill_switch` exercise |
| `independent-verification` | a retained evidence record |
| `security-review` | a retained evidence record |
| `error-budget-enforced` | a passing `error_budget_exhausted` exercise |
| `policy-fail-closed` | a passing `policy_outage` exercise |
| `audit-fail-closed` | a passing `audit_outage` exercise |
| `blast-radius-within-budget` | every counted exercise observed a radius within the certified budget |
| `minimum-successful-exercises` | at least `MIN_SUCCESSFUL_EXERCISES` (7) counted successes |

Three rules narrow what counts:

* **Rehearsals never count.** Any `ExerciseResult` whose `evidence_grade` is
  `rehearsal` is dropped before anything is counted, and the certifier reports
  `rehearsal-graded-exercises-excluded` so the exclusion is visible rather than
  silent.
* **Two items cannot be exercised.** `independent-verification` and
  `security-review` are human judgements. They must exist in the evidence
  registry as records with `decision: "l4-promotion"`, `scope:
  "<service>/<environment>/<runbook_id>"`, a `basis` that is not `modeled`, and
  a `claim` naming the control (`security-review`, `independent-verification`).
  See [`evidence/README.md`](evidence/README.md).
* **A failed or unreferenced exercise blocks.** Any failed exercise in scope, or
  any counted exercise with a blank `evidence_ref`, blocks certification.

## Producing the record

```bash
PYTHONPATH=. python scripts/certify_l4_scope.py \
  --exercises l3-exercises-<scope-hash>.json \
  --evidence-dir docs/evidence \
  --service payments --environment prod --runbook aks.rollout.undo \
  --blast-radius-budget 3 \
  --policy-bundle-version eip-remediation-v1 \
  --issued-by security@example.com
```

`--policy-bundle-version` must be the `policy_revision` the policy evaluator
reports in the target environment (`eip-remediation-v1` for the shipped rego
bundle, `local-reference` for the offline reference evaluator). It is part of the
material-inputs hash, so certifying against one bundle revision and executing
against another is refused.

Exit codes: `0` certified, `1` not eligible — the missing list is printed, `2`
the request itself was invalid.

The script **never writes into `docs/evidence/`** and refuses any `--output-dir`
under such a path. The registry holds reviewed claims; a certification is derived
from them and is a different artifact.

The script also refuses a platform identity for `--issued-by` (`ci`, `bot`,
`github-actions`, `platform`, …). **The platform cannot self-certify.** No
workflow, agent, or runner in this repository may sign a certification: the
signature names the person or team accountable for the promotion decision.

### Record format

```json
{
  "scope": {"service": "...", "environment": "...", "runbook_id": "...", "blast_radius_budget": 3},
  "scope_hash": "<sha256 hex of the canonical scope>",
  "inputs_hash": "<sha256 hex of the scope and its material inputs>",
  "exercises_digest": "sha256:<digest of the counted exercises>",
  "issued_on": "<ISO-8601>",
  "expires_on": "<ISO-8601>",
  "issued_by": "<person or team>",
  "evidence_ids": ["l4-security-review", "l4-independent-verification"],
  "policy_bundle_version": "eip-remediation-v1"
}
```

## What invalidates a certification

`architecture/l4-certification.md`: "Any material runbook, dependency, policy,
verification signal or blast-radius change invalidates the prior assurance and
requires recertification."

`resilience.scope.CertificationScope` makes that mechanical. Two hashes are
compared on every L4 execution:

* `scope_hash` — the service, environment, runbook id and blast-radius budget.
  Changing the service policy's `max_blast_radius` changes it.
* `inputs_hash` — the scope plus the runbook definition, the policy bundle
  version, the verification signal, and the runbook's declared dependencies.
  Changing a precondition, a verify signal, a rollback path, or the policy bundle
  revision changes it.

Either mismatch, or an `expires_on` in the past, refuses the execution. There is
no override flag. Recertify: rerun the exercises, retain the evidence, rerun
`certify_l4_scope.py`.

## What the execution path does

`remediation.executor.execute_control_loop` refuses in this order:

| Order | Condition | Result | Reason |
|---|---|---|---|
| 1 | `EIP_AUTONOMY_KILL_SWITCH=true` and `max(policy.level, raw declared)` ≥ L3 | `blocked` | `kill-switch` |
| 2 | the declared `autonomy_level` diverges from the policy other than by the one sanctioned downgrade | `blocked` | `autonomy-level: …` (names both levels) |
| 3 | L4 with no record / unreadable or past `expires_on` / wrong `scope_hash` / no scope hash | `blocked` | `l4-certification: …` |
| 4 | policy (OPA or the reference evaluator) denies | `denied` | the policy reason |
| 5 | L4 and `inputs_hash` differs from the current material inputs | `blocked` | `l4-certification: material inputs changed …` |

Ordering notes: the kill switch outranks everything, including a complete and
valid certification. Presence, expiry and scope are decided before the policy
service is contacted, so an uncertified L4 request never reaches it. The
material-inputs check runs last because the hash binds the policy bundle revision
that authorised the request, which is only known once the decision comes back.

### The declared level is a claim, not an authority

`autonomy_level` says what level a caller *believes* it is running at. The
reviewed `ServiceAutonomy` is what actually grants the level, so:

* an absent `autonomy_level` resolves to `policy.level`;
* a declared level **above** `policy.level` is refused;
* a declared level **below** `policy.level` is refused — with exactly one
  exception: `APPROVE_AND_EXECUTE` (L3) under an L4 policy, the supervised
  exercise path. The promotion rule makes supervised runs the *input* to
  certification, so they must not require the certification they exist to earn;
* the kill switch keys off `max(policy.level, raw declared)` — the claim as it
  arrived, before clamping — so neither a downgrade nor an over-declaration steps
  around it, and an operator with the switch engaged is told `kill-switch` rather
  than a level quibble.

Without this clamp a caller could declare L2 against an L4 policy and execute an
uncertified production mutation with the kill switch engaged. The refusal reason
names both levels.

L0–L2 are unaffected by both the kill switch and the certification gate.

### The policy boundary decides for itself

OPA is a separate authorization boundary, so the input document carries
`autonomy_level`, `scope: {scope_hash}`, `now`, and
`certification: {scope_hash, inputs_hash, expires_on}`.
`infra/policy/remediation-policy.rego` denies an L4 request whose certification
is absent, null, expired, unreadable, for another scope, or carrying no
material-inputs hash. It treats the declared level exactly as the executor does:
a declared `L4` always counts, the sanctioned `L3` downgrade does not, and
anything else — an absent field, an understated level — falls back to
`input.policy.level >= 4`. A request with `policy.level: 4` and no
`autonomy_level` at all is therefore denied without a certification, rather than
falling through the rule chain.

Two coercions in that rule are deliberately total, because in a non-strict OPA an
undefined value silently skips a rule rather than failing it:

* **only a string can carry a claim.** `trim_space()` on a `null`, a number, or
  an object is a builtin type error, which resolves to *undefined* — and an
  undefined `declared_level` would skip the whole `l4-certification` chain. The
  string path is gated on `is_string`, and a third `is_l4` body covers everything
  that is not a string, so `autonomy_level: null` and `autonomy_level: 4` under a
  level-4 policy are denied. `AutonomyContext.is_l4` gates on `isinstance(str)`
  for the same reason: coercing `None` to `"NONE"` with `str()` would give the
  right answer by coincidence, not by contract.
* **a policy must carry a reviewed level.** Every level-dependent rule reads
  `input.policy.level`; a missing or non-numeric one made each of them undefined
  and fell through to `allowed`. The bundle now denies once, immediately after
  the kill switch, with `service autonomy policy carries no reviewed level`. OPA cannot recompute the material-inputs hash — it would
have to reproduce the executor's canonical JSON of the runbook definition — so it
checks that one is present and bound to the right scope, and the executor
compares the value. `LocalReferenceEvaluator` mirrors the same rules so the
offline reference and the authoritative bundle cannot drift; `opa test /policy`
covers the allow and deny cases in CI.

## The kill switch

`EIP_AUTONOMY_KILL_SWITCH=true` (any casing, surrounding whitespace ignored)
refuses every L3 and L4 execution with the fixed reason `kill-switch`, before
policy, approval and certification are considered. It is deliberately permissive
about what counts as "on" and it has no per-scope exemption.

## What this runbook does not claim

No scope in this repository is certified. No certification record exists here,
and `docs/evidence/` contains no `l4-promotion` record. The gate being
implemented and tested is not evidence that anything passed through it.
