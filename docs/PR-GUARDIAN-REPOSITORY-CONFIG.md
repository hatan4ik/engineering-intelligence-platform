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
5. the configured `expires_on` has not passed;
6. the kill switch is off.

Any disagreement degrades the published conclusion to `neutral` and the reason
is printed in the sticky comment. The observation can only ever lower what is
published; it can never raise it.

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
`architecture: {violations, summary}`. The publisher renders them into the
sticky comment.

Architecture findings are **advisory in every mode**. They never change a check
conclusion and they are not part of any enforcement rule.

Content is fetched read-only through the GitHub contents API at the pull
request's head SHA — the head revision is never checked out and never executed.
Files whose content cannot be read are not reviewed and never become findings.

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
    "summary": "1 architecture finding(s) across 1 file(s)."
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
- It does not tune `threshold` from observed outcomes. Calibration output is a
  recommendation for a human; nothing writes back into this file.
- It does not block on Architecture Guard findings.
- It does not treat an expired approval as a renewed one.
