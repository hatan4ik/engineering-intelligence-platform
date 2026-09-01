# PR Guardian Advisory Promotion Review

| | |
|---|---|
| **Status** | Review-packet contract; no advisory decision or retained pilot evidence exists in this repository |
| **Feedback source** | [`PR-GUARDIAN-SHADOW-REPORT.md`](PR-GUARDIAN-SHADOW-REPORT.md) |
| **Pilot operation** | [`PR-GUARDIAN-SHADOW-PILOT.md`](PR-GUARDIAN-SHADOW-PILOT.md) |
| **Evidence standard** | [`PRODUCTION-EVIDENCE.md`](PRODUCTION-EVIDENCE.md) |

## Purpose

An `advisory-candidate` shadow report is enough to request a human evidence review, not to enable
advisory mode. The typed contract in
[`feedback/pr_guardian_promotion.py`](../feedback/pr_guardian_promotion.py) produces an expiring
packet that binds five external evidence categories to the exact canonical digests of the generated
report and its normalized closure-record export.

The validator is deliberately non-authorizing. It performs no GitHub or cloud calls, cannot create
an evidence record, cannot move a repository beyond `shadow`, and always reports
`advisory_or_enforcement_authorized=False`.

## Preconditions for a packet

Only prepare a packet after the report has all five internally calculated requirements:

- at least 30 joined observations and 30 explicit reviewer classifications;
- at least 5 reviewer-confirmed risks;
- simulated-block precision of at least 0.50 and recall of at least 0.80; and
- `decision: "advisory-candidate"` with `blocking_authorized: false`.

The packet then requires exactly one retained, externally controlled reference for each category:

| Evidence category | Required basis | Why it is needed |
|---|---|---|
| `shadow-outcome-export` | measured | The normalized human-feedback inputs behind the report digest |
| `shadow-report` | derived | The exact generated metrics and candidate decision |
| `citation-quality-review` | measured or derived | Evidence and provenance quality review |
| `performance-and-cost-report` | measured or derived | Latency, cost, and operational-budget evidence |
| `independent-post-merge-correlation` | measured | Outcome signal from an observer independent of the action path |

Every reference declares an external system, immutable locator, SHA-256 content digest, at least
90-day retention, access-control and immutability controls, and accountable producer. The independent
post-merge correlation additionally requires a different verifier identity. An Actions artifact or
run URL is rejected as the evidence destination.

## Operator sequence

1. Export closure records and the generated report to the approved immutable evidence system. Do
   not use a PR comment or an Actions artifact as the evidence record.
2. Record the real external evidence IDs, immutable locators, SHA-256 digests, and actual
   accountable identities in a review packet stored with the review material. Bind the pilot
   manifest and runtime configuration digests, and keep `runtime_mode` as `shadow`.
3. Give the packet a short, explicit review expiry; stale evidence must be regenerated rather than
   silently re-used.
4. Validate the packet against the original generated report from a trusted checkout:

   ```bash
   PYTHONPATH=. python scripts/validate_pr_guardian_promotion_packet.py \
     --packet /path/to/pr-guardian-advisory-review-packet.json \
     --shadow-report /path/to/pr-guardian-shadow-report.json
   ```

5. Obtain the actual service-owner, Security/SRE, and Developer Experience review outside this
   validator. If they decide to enable a non-blocking advisory check, make that change through the
   target repository's separately reviewed configuration process described in
   [`PR-GUARDIAN-REPOSITORY-CONFIG.md`](PR-GUARDIAN-REPOSITORY-CONFIG.md).

## Boundaries that remain external

Passing this validation does **not** attest that data was collected in a named pilot, that an
evidence reference resolves, that a human signed off, or that the review approved a configuration
change. It cannot create the first retained record in [`evidence/`](evidence/README.md), and it
must never be interpreted as a promotion decision. A service owner’s independent, expiring
repository configuration is still required even after a complete evidence review.
