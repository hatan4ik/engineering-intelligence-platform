# PR Guardian Shadow Pilot

| | |
|---|---|
| **Status** | Repository-ready shadow-pilot workflow; no pilot evidence has yet been collected |
| **Autonomy** | L0/L1 advisory only; it cannot approve, block, or modify a merge decision |
| **Evidence contract** | [`PRODUCTION-EVIDENCE.md`](PRODUCTION-EVIDENCE.md) |
| **Product scope** | [`PRODUCT-STRATEGY.md`](PRODUCT-STRATEGY.md) |

## Purpose and boundary

PR Guardian calculates deterministic change risk from the pull-request diff and the checked-in
service graph. In this pilot it produces a **simulated** policy decision (`would block`, `would
require additional approval`, or `would require extended tests`). It does not enforce that
decision. Every published check has the separate name `Engineering Intelligence / PR Guardian
(shadow)` and the GitHub `neutral` conclusion.

Do not add this workflow or check to branch protection as a required gate. A neutral check does
not block a merge, but an unavailable workflow could still become an operational dependency if
made required. The pilot must remain optional until an approved promotion review says otherwise.

## Safe workflow split

```text
pull_request (read-only token, base revision only)
  -> validated shadow-result artifact
  -> workflow_run (trusted default-branch code)
  -> neutral check + advisory PR comment

pull_request_target: closed (trusted default-branch code; no PR checkout)
  -> reviewer labels + matching advisory record
  -> closure artifact + best-effort calibration comment
```

The first workflow does not receive a write-capable token and does not execute the pull-request
head revision. The publisher validates the artifact schema, repository, event type, and head SHA
before it has permission to create a check or comment. It accepts marker comments only when they
were written by its authenticated automation identity, so a contributor cannot forge a prior
observation. The closure workflow reads the GitHub event as data and checks out the default branch
only. It has no deployment or cloud credentials.

The closure artifact is written before the calibration comment is attempted. If GitHub refuses that
comment, the workflow records `publication=not-published` and retains the artifact for investigation;
it must not discard the captured reviewer disposition. The artifact is still only short-retention
workflow output, not promotion evidence, and a failed comment remains an operational gap to resolve.

For an authenticated GitHub webhook, the bounded `X-GitHub-Delivery` identifier is preserved as
the PR finding, workflow, audit, telemetry, and response correlation ID. An internal caller with
no upstream identifier receives a newly minted correlation ID; neither path creates a second ID
mid-workflow.

Fork PRs are expected to have a read-only `GITHUB_TOKEN`; this design deliberately accommodates
that restriction by publishing only from the subsequent trusted workflow.

## Reviewer input

Before enabling the workflows, a repository administrator creates these exact labels:

| Signal | Label | Meaning |
|---|---|---|
| Risk | `eip-pr-guardian/confirmed-risk` | Reviewer agrees the finding represents material risk |
| Risk | `eip-pr-guardian/false-positive` | Reviewer judges the material finding incorrect/noisy |
| Utility | `eip-pr-guardian/useful` | Output helped the review |
| Utility | `eip-pr-guardian/not-useful` | Output was not useful |

Apply at most one label in each signal group. Absence of a label means **not reviewed**; closing
or merging a PR is never interpreted as evidence that the risk assessment was right. Conflicting
labels fail the closure record rather than silently choosing one.

## Pilot operation

1. Before enabling anything, create and validate a repository-owned shadow-pilot manifest using
   [`PR-GUARDIAN-PILOT-ONBOARDING.md`](PR-GUARDIAN-PILOT-ONBOARDING.md). It records the actual
   accountable owners, retention controls, and workflow safety posture, but cannot activate a
   pilot or authorize advisory/enforcement mode.
2. Enable the three checked-in workflows and verify that `PR Guardian Shadow (non-blocking)` is
   not a required status check/ruleset condition.
3. Collect a representative sample across the selected repository or repositories. Add reviewer
   labels to every material finding, including negative feedback.
4. At closure, confirm the retained artifact records the matching shadow score and reviewer signal.
   The `PR Guardian shadow-pilot closure record` comment is a convenience surface; if it is missing,
   investigate its recorded publication state. A missing match is a data-quality gap, not a benign result.
5. Export the short-retention closure artifacts to the approved immutable evidence system with
   repository, time window, workflow revision, reviewer, and access-control metadata. An Actions
   artifact or PR comment alone is not an evidence record.
6. Run the offline report over that approved export. For example, from a read-only export copy:

   ```bash
   python scripts/summarize_pr_guardian_shadow.py approved-shadow-export/ \
     --output /tmp/pr-guardian-shadow-report.json
   ```

   The report always returns `blocking_authorized: false`. It is a calibration input, not an
   automatic promotion mechanism.

## Minimum review packet

A candidate promotion packet needs, at a minimum:

- 30 joined shadow observations and 30 explicit reviewer classifications;
- at least 5 reviewer-confirmed risks;
- simulated-block precision of at least 0.50 and recall of at least 0.80, with severity slices;
- false-positive, false-negative, no-match, latency, cost, and citation-quality analysis;
- service-owner approval, Security/SRE review, an expiry date, waiver procedure, and a tested
  disable/rollback path; and
- post-merge incident/rollback correlation from an independent operational source.

Meeting the numeric thresholds does **not** authorize enforcement. The evidence must be retained
and reviewed under [`PRODUCTION-EVIDENCE.md`](PRODUCTION-EVIDENCE.md); only then may owners
consider a separately reviewed, deterministic blocking proposal.

## Stop conditions

Pause the pilot and return to no-publish mode if any of these occur:

- GitHub workflow changes cause PR-head code to run with a write token or cloud/deployment secret;
- a shadow result is published as a `failure`, `action_required`, or a required branch gate;
- an artifact/closure record cannot be bound to the same repository, PR number, and head SHA;
- conflicting or missing reviewer inputs invalidate a material portion of the sample;
- the check leaks restricted data, lacks adequate evidence, or materially harms reviewer workflow.

No exception converts a shadow result into a merge decision. Disable by removing the workflows or
their repository enablement; preserve already-exported evidence for the review record.
