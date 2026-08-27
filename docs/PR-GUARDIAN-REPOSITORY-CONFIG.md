# PR Guardian repository configuration

PR Guardian reads one file from the repository it evaluates:

```
.eip/pr-guardian.json
```

JSON, not YAML: the runtime has no YAML parser and reading a policy file must
not add a dependency.

**If the file is absent, the repository is in `shadow` mode.** Nothing else is
assumed: no owner, no service, and no evidence source is claimed on the
repository's behalf.

Enabling `enforce` is a service-owner decision recorded in the config; the
platform cannot enable it.

---

## Schema

```json
{
  "mode": "shadow",
  "service_ids": ["payments"],
  "service_owners": ["octocat", "team-payments"],
  "policy_version": "pr-policy-2026-08",
  "evidence_sources": ["github-pull-request"],
  "enforcement": null
}
```

| Field | Required | Meaning |
| --- | --- | --- |
| `mode` | yes | `shadow`, `advisory`, or `enforce`. |
| `service_ids` | yes | Non-empty list of services this repository owns. |
| `service_owners` | yes | Non-empty list of GitHub logins that may approve enforcement and sign waivers. |
| `policy_version` | yes | The policy revision this configuration was written against. |
| `evidence_sources` | no | Defaults to `["github-pull-request"]`. |
| `repository` | no | If present it must equal the repository being evaluated. |
| `enforcement` | only when `mode` is `enforce` | The owner-signed enforcement block below. Supplying it in any other mode is an error. |

Identifier lists may be written in any order — they are normalized to sorted
order — but a duplicate entry is an error, so the file stays unambiguous.

### The `enforcement` block

```json
{
  "mode": "enforce",
  "service_ids": ["payments"],
  "service_owners": ["octocat"],
  "policy_version": "pr-policy-2026-08",
  "enforcement": {
    "rule": "iac-change-without-test-evidence-at-high-risk",
    "threshold": 70,
    "approved_by": "octocat",
    "approved_on": "2026-08-01",
    "expires_on": "2026-12-31",
    "waivers": [
      {
        "path_glob": "infra/legacy/*.tf",
        "reason": "Frozen legacy stack; owner accepts the risk until Q4.",
        "owner": "octocat",
        "expires_on": "2026-10-01"
      }
    ]
  }
}
```

| Field | Meaning |
| --- | --- |
| `rule` | Exactly one rule id from the closed set below. |
| `threshold` | Integer 0–100. The deterministic risk score at or above which the rule may fire. |
| `approved_by` | A login that also appears in `service_owners`. |
| `approved_on` | ISO date (`YYYY-MM-DD`) the owner approved enforcement. |
| `expires_on` | ISO date. **Mandatory.** Enforcement lapses on its own after this date. |
| `waivers` | Up to 64 entries; see below. May be omitted or empty. |

### Rules

Exactly two rule ids exist. Both are deterministic functions of the changed
file list and the risk assessment; nothing else can ever fail a check.

| `rule` | Fires when all of these hold |
| --- | --- |
| `iac-change-without-test-evidence-at-high-risk` | the change touches infrastructure-as-code (`*.tf`, `*.tfvars`, `infra/`, `terraform/`, `helm/`, `k8s/`), the assessment carries both the `infrastructure-change` and `weak-test-evidence` factors, and `score >= threshold` |
| `security-boundary-change-without-test-evidence-at-high-risk` | the change touches an identity/security boundary path, the assessment carries both the `security-boundary-change` and `weak-test-evidence` factors, and `score >= threshold` |

### Waivers

A waiver is a named owner's time-boxed exemption for one path glob.

| Field | Meaning |
| --- | --- |
| `path_glob` | `fnmatch` pattern, e.g. `infra/legacy/*.tf`. |
| `reason` | Why the exemption exists. Free text, required. |
| `owner` | A login that also appears in `service_owners`. |
| `expires_on` | ISO date. A waiver past this date is ignored. |

A waiver bypasses the rule **only when it covers every file the rule fired
on**. If a change touches `infra/legacy/old.tf` and `infra/payments/main.tf`,
a waiver for `infra/legacy/*.tf` does not excuse it — the un-waived file still
carries the risk the owner did not accept.

### Invalid configurations

Every validation error names the offending field, for example
`enforcement.expires_on ... has passed` or `waivers[0].owner must name one of
the declared service_owners`. The following are errors:

- an unrecognized top-level, `enforcement`, or waiver field;
- `mode: "enforce"` without an `enforcement` block, or an `enforcement` block
  in any other mode;
- `enforcement.expires_on` earlier than `approved_on`, or already in the past;
- `approved_by` or a waiver `owner` that is not in `service_owners`;
- a `rule` outside the closed set, or a `threshold` outside 0–100;
- a `repository` value that names a different repository;
- a file that is not valid JSON.

---

## What each mode publishes

The evaluation workflow (`pr-guardian.yml`) has a read-only token, runs on the
pull request's **base** commit, publishes nothing, and **always exits 0**. It
writes an observation artifact. The publisher workflow
(`pr-guardian-shadow-publish.yml`) has write scope, runs default-branch code,
and is the only writer.

| Mode | Check name | Conclusion | Title |
| --- | --- | --- | --- |
| `shadow` | `Engineering Intelligence / PR Guardian (shadow)` | always `neutral` | `Shadow risk: …` |
| `advisory` | `Engineering Intelligence / PR Guardian (advisory)` | always `neutral` | `Advisory risk: … — this check does not block merges` |
| `enforce` | `Engineering Intelligence / PR Guardian (enforce)` | `failure` only when the rule fired and no waiver applied; otherwise `neutral` | `Blocked by <rule>: …` or `Enforcing risk: … — not blocked` |

`shadow` behaviour is unchanged from the shadow pilot.

The sticky comment states the authority the mode actually has, and there is one
rendering path (`product.pr_guardian_shadow.observation_comment`) for all three
modes. In `shadow` it still says the result cannot change merge status; in
`advisory` it says it is a non-blocking check for this repository's certified
scope; in `enforce` it names the rule, says whether the change would block this
pull request, and names the owner of any waiver that applied. When the publisher
re-derives a different conclusion than the observation claimed, the comment
discloses the conclusion that was actually published and why.

Marking the check required in branch protection is a repository decision and is
independent of this file. In `shadow` and `advisory` the check can never report
`failure`, so making it required has no gating effect.

### The publisher re-derives the conclusion

The observation is produced by a job that ran against untrusted pull-request
content. The publisher therefore re-reads `.eip/pr-guardian.json` from the
**default-branch** checkout and re-decides. It publishes `failure` only when all
of these hold:

1. the observation's `mode` is `enforce`;
2. the observation's `enforcement.would_block` is `true`;
3. the default-branch configuration is also in `enforce` mode;
4. the observation's `enforcement.rule` equals the configured rule;
5. the observation's `assessment.score` is at least the configured `threshold`;
6. the configured `expires_on` has not passed;
7. the kill switch is off.

Any disagreement degrades the published conclusion to `neutral` and the reason
is printed in the sticky comment.

### Threat model: what the re-read does and does not prevent

**It constrains escalation only.** The re-read stops an observation from
producing a `failure` the default-branch configuration does not authorize: a
forged `would_block: true`, a rule the repository did not select, a score below
the configured threshold, or a mode the repository never enabled all degrade to
`neutral`.

**It does not stop a pull request from evading its own enforcement.** The
evaluation workflow is `pull_request`-triggered, so GitHub runs the workflow
*definition from the pull request's head*. A pull request that edits
`.github/workflows/pr-guardian.yml` can therefore upload any artifact it likes
— including one reporting `would_block: false` — and because the publisher only
constrains the escalation direction, that artifact publishes `neutral`. A pull
request cannot make the check *fail* for someone else, and it cannot raise its
own repository's mode (the configuration is read from the base commit and
re-read from the default branch), but it **can** suppress a block on itself.

Selective enforcement is therefore only as strong as the review on the two
paths that define it. A repository that enables `enforce` should require human
review on both:

```
# .github/CODEOWNERS
/.github/workflows/   @your-org/service-owners
/.eip/                @your-org/service-owners
```

with a branch protection rule that requires review from Code Owners and
dismisses stale approvals. Without that, treat `enforce` as a strong default
that an author can opt out of in the open — visible in the diff — rather than
as a control.

### When the publisher cannot trust its inputs

Neither failure mode may take the publisher down, because a repository in
`enforce` mode is the one most likely to have marked this check required — a
crashing publisher would block merges through the platform's own failure.

- **A missing, unparseable, or invalid evaluation artifact** (including one
  whose repository or head SHA does not match the triggering run) publishes a
  `neutral` check titled "PR Guardian could not verify this evaluation", with a
  comment naming the reason. The publisher workflow then exits non-zero so an
  operator sees it, while the pull request stays unblocked.
- **An unreadable `.eip/pr-guardian.json`** degrades to shadow, publishes
  `neutral`, and states the parse error in the comment.
- **A lapsed `enforcement.expires_on`** still loads — an expired approval is a
  well-formed statement of intent, not a corrupt file — and the publisher
  reports `enforcement-approval-expired` and publishes `neutral`. Refusing to
  load it would mean every publish run in that repository died on the day the
  approval expired.

Authoring is stricter than loading: writing a configuration whose `expires_on`
has already passed is an error, so the mistake is caught when the file is
validated rather than silently accepted.

---

## Kill switch

```
EIP_PR_GUARDIAN_KILL_SWITCH=true
```

Only the exact value `true` (case-insensitive, surrounding whitespace ignored)
disables enforcement; any other value leaves the configuration in force.

Set it as a **repository variable** named `EIP_PR_GUARDIAN_KILL_SWITCH`; both
workflows pass it through. It forces `would_block=false` with
`reason="kill-switch"` in the evaluation job and forces a `neutral` conclusion
in the publisher, regardless of what the configuration says. It requires no
change to `.eip/pr-guardian.json` and no code deployment.

The mandatory `enforcement.expires_on` is the second, slower off switch:
enforcement lapses by itself unless a human re-approves it.

---

## Architecture Guard on the pull-request path

After risk assessment, the evaluation job runs the deterministic architecture
rules in `product/architecture_review.DEFAULT_ARCHITECTURE_RULES` over the
changed files and records the findings in the observation as
`architecture: {violations, in_scope, reviewed, skipped, summary}`. The
publisher renders them into the sticky comment.

Architecture findings are **advisory in every mode**. They never change a check
conclusion and they are not part of any enforcement rule.

Content is fetched read-only through the GitHub contents API at the pull
request's head SHA — the head revision is never checked out and never executed.

**Coverage is reported, not assumed.** A file that matched a rule but whose
content could not be fetched (deleted, a submodule, too large, not UTF-8 text,
or an API error) is counted in `skipped` with its reason, never treated as
clean. `in_scope` counts the changed files some rule could match and `reviewed`
counts those actually read, so:

- `in_scope == 0` → "No changed file was in scope for an architecture rule."
- `reviewed == 0` with files in scope → "Architecture Guard did not run:
  content was unavailable for all N in-scope file(s)". It never reports an
  absence of findings about files it did not read.
- otherwise the summary states how many of the in-scope files were reviewed and
  how many were skipped, and the comment lists each skipped path and reason.

---

## Observation record

The workflow-transfer record gained three fields. Records written before these
existed still validate; the missing sections are filled with their explicitly
non-blocking, empty defaults.

```json
{
  "mode": "enforce",
  "enforcement": {
    "would_block": true,
    "reason": "rule-condition-met",
    "rule": "iac-change-without-test-evidence-at-high-risk",
    "waived_by": null
  },
  "architecture": {
    "violations": [
      {
        "rule_id": "EIP-ARCH-001",
        "path": "infra/app/main.tf",
        "marker": "public_network_access_enabled = true",
        "rationale": "Managed data planes must stay on private endpoints.",
        "severity": 4
      }
    ],
    "in_scope": 3,
    "reviewed": 2,
    "skipped": [{"path": "infra/big.tfvars", "reason": "larger than 512000 bytes"}],
    "summary": "1 architecture finding(s) across 1 file(s). Reviewed 2 of 3 in-scope file(s). 1 file(s) could not be reviewed."
  }
}
```

`enforcement.reason` is one of `kill-switch`, `mode-not-enforcing`,
`enforcement-approval-expired`, `rule-condition-not-met`, `waived-by-owner`, or
`rule-condition-met`. A record may claim `would_block: true` only in `enforce`
mode and only while naming the rule that produced it.

---

## What this does not do

- It does not let the platform enable, escalate, or extend enforcement. Every
  path to `failure` runs through a file in the repository, changed by that
  repository's own review process.
- It does not stop a pull request that edits `.github/workflows/` from
  suppressing a block on itself. See "Threat model" above; require Code Owner
  review on `.github/workflows/` and `.eip/` if that matters to you.
- It does not tune `threshold` from observed outcomes. Calibration output is a
  recommendation for a human; nothing writes back into this file.
- It does not block on Architecture Guard findings.
- It does not treat an expired approval as a renewed one.
