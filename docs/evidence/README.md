# Evidence registry

| | |
|---|---|
| **Classification** | Current implementation state (registry mechanics) |
| **Owner** | Platform Engineering, with the service owner named in each record |
| **Contract** | [`../PRODUCTION-EVIDENCE.md`](../PRODUCTION-EVIDENCE.md) |
| **Code** | [`../../validation/evidence_records.py`](../../validation/evidence_records.py), [`../../scripts/record_evidence.py`](../../scripts/record_evidence.py) |
| **Production claim** | None. This directory holds records; it does not certify anything |

## An empty directory means *not proven*

This directory ships with nothing but this README. That is the accurate state: no promotion
decision in this repository is backed by a retained evidence record. An empty registry must never
be read as "not yet documented but fine", and a maturity score, status label, or green CI run may
never be substituted for a missing record.

## What belongs here

One immutable JSON record per exercise, integration run, or promotion decision, named
`<evidence_id>.json`. A record describes a **real run in a named scope**. It is an index of
evidence, not the evidence itself: the artifacts it references live in the approved audit/evidence
system, and a GitHub Actions artifact may be an input but is never the sole record.

What does not belong here: sample or illustrative records, records for runs that did not happen,
records copied from another environment, and anything that has to be edited after the fact
(records are immutable — supersede, do not rewrite).

For a latency, capacity, queue, or cost claim, validate the separate report against the
[`../PERFORMANCE-EVIDENCE-CONTRACT.md`](../PERFORMANCE-EVIDENCE-CONTRACT.md) and link that
retained report in this record's `artifacts`. The baseline's target numbers are not evidence and
must not be copied here as if they were observed results.

## Record schema

Every record carries the nine fields of the evidence-record table in
[`../PRODUCTION-EVIDENCE.md`](../PRODUCTION-EVIDENCE.md), plus `basis`, `decision`, and — for
measured records — `source_run_url`.

| Field | Required content |
|---|---|
| `evidence_id` | Immutable unique identifier; lowercase, filename-safe, and equal to the file name without `.json` |
| `scope` | Repository/service, environment, region, tenant/data classification, and autonomy tier |
| `change` | Git SHA, image digest, IaC version, model/deployment, prompt, policy bundle, and runbook version |
| `claim` | Exact requirement or certification control being proven |
| `method` | Test, drill, shadow sample, restore exercise, or independently observed operational window |
| `result` | Pass/fail, quantitative result, timestamps, sampled population, and known limitations |
| `independence` | Identity of the verifier and why its signal is independent of the action path |
| `artifacts` | List of signed links/digests for logs, traces, audit export, dashboards, and review record |
| `approval` | Service owner, Security/SRE reviewer, expiry, and exception/waiver reference if any |
| `basis` | `measured`, `derived`, or `modeled` (see below) |
| `decision` | One of `real-data-pilot`, `pr-guardian-advisory`, `blocking-pr-rule`, `l3-remediation-pilot`, `l4-promotion` |
| `source_run_url` | The run the result was measured from. **Required** when `basis` is `measured` |
| `readiness_key` | Optional. The production-readiness item this record proves — one of the keys in `validation.production_readiness.REQUIRED_KEYS` (`real-source-integration`, `entra-production-auth`, `private-network-path`, `ha-state-backend`, `backup-restore-drill`, `audit-export`, `security-adversarial-suite`, `control-plane-slo`, `production-like-soak`, `rollback-drill`, `kill-switch-drill`, `independent-verification`) |
| `controls` | Optional list. The L4 certification controls this record attests, by exact name from `resilience.certification.ATTESTED_CONTROLS` — today `security-review` and `independent-verification` (the two mandatory items in [`../../architecture/l4-certification.md`](../../architecture/l4-certification.md) that no exercise can demonstrate). Any other name is rejected at validation |

### What readers key on

Readers never parse `claim`. `claim` is for humans.

- `scripts/production_readiness_report.py` counts a record toward a readiness item only when
  `readiness_key` names that item **and** the first `;`-separated segment of `result` is exactly
  `pass` (so `"pass; 2/2 principals behaved as required; limitations: single region"` passes and
  `"passed with caveats"` does not) **and** `artifacts` lists at least one retained reference.
- `scripts/certify_l4_scope.py` counts a record as attesting a control only when that control's
  exact name appears in `controls`, the record's `decision` is `l4-promotion`, its `scope` equals
  the certification scope, and its `basis` is not `modeled`.

A record without these fields is still a valid record; it just proves nothing to those readers.

### `basis`

| Value | Meaning |
|---|---|
| `measured` | Observed in an actual run in the recorded scope. Must cite `source_run_url` |
| `derived` | Computed from one or more measured records (for example an aggregate rate) |
| `modeled` | Simulation, rehearsal, or digital-twin output. Never production proof on its own |

## Writing a record

```bash
PYTHONPATH=. python scripts/record_evidence.py \
  --evidence-id 2026-09-integration-proof-westeurope \
  --scope "acme/platform, integration, westeurope, internal, L0" \
  --change "sha=<git sha> image=<digest> iac=<version> policy=<bundle>" \
  --claim "An unauthorized principal cannot retrieve protected evidence" \
  --readiness-key real-source-integration \
  --method "Read-only integration probe (docs/INTEGRATION-PROOF-RUNBOOK.md)" \
  --result "pass; 2/2 principals behaved as required; limitations: single region" \
  --independence "SRE on-call reviewed; verifier is not the deploying identity" \
  --artifact "https://…/run/123#sha256:<digest>" \
  --approval "owner=@service-owner reviewer=@sre expiry=2027-03-01" \
  --basis measured \
  --decision real-data-pilot \
  --source-run-url "https://…/run/123"
```

An L4 attestation adds `--decision l4-promotion` and one `--control <name>` per control it attests.

The CLI refuses to overwrite an existing record, refuses `--basis measured` without
`--source-run-url`, and reports every schema violation at once.

## Reading the registry

`validation.evidence_records.load_registry(directory)` validates and returns every record;
`registry_summary(records)` groups them by decision, scope, and basis and lists the decisions with
no records at all. The summary reports absence only — it never states that a decision is proven.

## Expiry

Evidence expires when the scoped service, environment, data classification, identity model,
model/prompt, policy, runbook, or infrastructure materially changes. An expired record reverts the
related capability to the previous safe autonomy tier until requalified. Record the expiry in
`approval`.
