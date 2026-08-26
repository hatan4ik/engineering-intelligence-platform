# PR Guardian Shadow Report

| | |
|---|---|
| **Purpose** | Summarize retained shadow-pilot closure records into one reviewable report |
| **Autonomy** | None — the report never changes a check, a threshold, or a merge decision |
| **Producer** | [`.github/workflows/pr-guardian-shadow-report.yml`](../.github/workflows/pr-guardian-shadow-report.yml) |
| **Pilot contract** | [`PR-GUARDIAN-SHADOW-PILOT.md`](PR-GUARDIAN-SHADOW-PILOT.md) |
| **Evidence contract** | [`PRODUCTION-EVIDENCE.md`](PRODUCTION-EVIDENCE.md) |

## What the report contains

`scripts/summarize_pr_guardian_shadow.py` reads the closure records produced by
`pr-guardian-shadow-outcome.yml` and writes `pr-guardian-shadow-report.json`:

- **`sample`** — how many closure records were read, how many joined a prior shadow observation,
  how many carry an explicit reviewer classification, how many were confirmed risks, and how many
  carry a utility signal.
- **`simulated_block_decision`** — the confusion matrix of the *simulated* block decision against
  the reviewer labels, with precision and recall. `null` where the denominator is zero.
- **`utility`** — reviewer `useful` / `not-useful` counts and rate.
- **`promotion_readiness`** — the five requirements from the pilot's minimum review packet, the
  list of `unmet_requirements`, the `decision`, a `next_review` hint, and `blocking_authorized`.
- **`calibration`** — suggested high-risk thresholds (see below).
- **`limitations`** — what the numbers cannot establish.

## `decision`

| value | meaning |
|---|---|
| `shadow-only` | At least one of the five promotion requirements is unmet, or there are no records. |
| `advisory-candidate` | All five requirements are met. |

`advisory-candidate` authorizes exactly one thing: **a human evidence review** of a promotion
packet under [`PRODUCTION-EVIDENCE.md`](PRODUCTION-EVIDENCE.md). It does not authorize advisory
mode, enforcement, a branch-protection change, or any threshold change. `blocking_authorized` is
`False` in every report, including one where all five requirements are met — no computed result
can authorize merge blocking.

`next_review` is a hint, not an instruction: `"no closure records yet"` when the input set is
empty, `"awaiting <first unmet requirement>"` while requirements are outstanding, and
`"human evidence review of the promotion packet"` once they are all met.

## Calibration

The `calibration` section turns reviewer dispositions into
`intelligence.risk_calibration.ScoredOutcome` samples, runs them through
`calibrate_high_risk_threshold`, and reports what a high-risk threshold *could* be:

- A reviewer-confirmed risk is a **failed** sample and a false positive is **not failed**, because
  the calibrator tunes a threshold to catch the failed class. The section publishes this as
  `disposition_mapping` (`confirmed-risk` → `failed`, `false-positive` → `not-failed`) and
  `failure_samples_from: "confirmed-risk"`, so a suggested threshold cannot be read in the wrong
  direction.
- Records with no reviewer disposition, and records that never joined a shadow observation (so
  carry no risk score), are excluded from every count in the section.
- `service_key` is `subject.repository`: a closure record identifies its scope only by repository,
  so "per service" here means per repository.
- `global` covers every reviewed record; each `per_service` entry re-runs the calibrator over that
  repository's samples alone. Both report the suggested threshold, sample size, failed samples,
  whether it differs from the default, a confidence value, and the calibrator's evidence strings.
  Below the calibrator's safety minimums (30 samples, 5 failures) the default threshold is
  retained and `changed_from_default` is `false`.
- `applied` is always `false`, alongside the sentence *"Threshold changes are reviewed product
  decisions; this section is a recommendation only."*

Nothing in this codebase reads the calibration section. Changing a risk threshold is a reviewed
product decision applied deliberately by a human, never an automatic consequence of a report.

## How the workflow produces it

`.github/workflows/pr-guardian-shadow-report.yml` runs on `workflow_dispatch` and weekly on a
schedule. It has read-only permissions (`actions: read`, `contents: read`) and:

1. checks out the default branch;
2. lists successful `pr-guardian-shadow-outcome.yml` runs on the default branch and downloads each
   run's retained `pr-guardian-shadow-outcome*` artifact with `gh run download` — a run whose
   artifact has passed its 14-day retention window is skipped, not an error;
3. if **zero** artifacts were downloaded, writes to the job summary that no retained artifacts were
   found and that this is not a result, and produces no report. The job succeeds;
4. otherwise runs the summarizer, uploads `pr-guardian-shadow-report.json` as an artifact with
   90-day retention, and prints the decision, sample counts, and unmet requirements to the job
   summary.

Run it locally over an approved export instead:

```bash
PYTHONPATH=. python scripts/summarize_pr_guardian_shadow.py approved-shadow-export/ \
  --output /tmp/pr-guardian-shadow-report.json
```

The script exits 0 on an empty input set and writes a report with `sample.closure_records: 0` and
`decision: "shadow-only"` rather than failing or inventing a sample.

## What this report is not

An Actions artifact is not an evidence record. The report is an *input* to the approved evidence
process: the closure records must still be exported to the immutable evidence system with
repository, time window, workflow revision, reviewer, and access-control metadata. Reviewer labels
are calibration signal, not post-merge incident or rollback outcomes.
