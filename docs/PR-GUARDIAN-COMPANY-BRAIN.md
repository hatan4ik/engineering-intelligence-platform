# PR Guardian and the Qualified Company Brain

| | |
|---|---|
| **Classification** | Reference contract — not a pilot, merge gate, or production assertion |
| **Product** | [PR Guardian](PRODUCT-STRATEGY.md), the first Company Brain interface |
| **Core query** | [`company_brain/world_model.py`](../company_brain/world_model.py) |
| **Adapter** | [`product/pr_guardian/company_brain.py`](../product/pr_guardian/company_brain.py) |
| **Durable product records** | [`product/pr_guardian/store.py`](../product/pr_guardian/store.py) |

PR Guardian is the first user-facing Company Brain interface. It consumes a tenant-scoped,
ACL-filtered [qualified world-model context](COMPANY-BRAIN-WORLD-MODEL.md), not raw graph data or
an unscoped vector result.

## Decision boundary

For every PR review, the adapter produces a reproducible `context_version` fingerprint and a
minimal `EvidenceBundle`. It uses qualified repository membership to map changed files to services;
then it uses only fresh, authorized, sufficiently confident relationships to build the blast-radius
graph. The fingerprint is retained with the finding, not treated as a mutable database version.

A context is **unqualified** if it lacks an affected service or authorized evidence, has stale or
low-confidence relationships, has a conflict (for example ambiguous ownership), or reports a
limitation. An unqualified context can still publish a neutral shadow observation, but its finding
must use `simulated_action = none`. It cannot request tests, extra approval, or a simulated block.

This is deliberate: unqualified knowledge is a prompt for a human to improve organizational memory,
not authority for the platform to invent a control.

## Durable learning records

[`SqlitePRGuardianStore`](../product/pr_guardian/store.py) retains immutable `PRFinding` records
and append-only explicit `FindingOutcome` records. Replaying the exact same record is idempotent;
reusing a finding ID with changed contents fails. A merge, close, or silence is not a reviewer
judgment and is therefore never stored as one.

Findings bind all of the following:

- PR repository, number, and head SHA;
- workflow correlation ID and deterministic policy version;
- world-model context fingerprint and qualification state; and
- authorized evidence pointers and their limitations.

## Runtime configuration

`EIP_PR_GUARDIAN_WEBHOOK=enabled` always retains findings in
`$EIP_STATE_DIR/pr-guardian.db`. To replace the checkout-derived graph with qualified Company Brain
context, configure all three values together:

```text
EIP_COMPANY_BRAIN_DB=/secure/state/company-brain.db
EIP_COMPANY_BRAIN_TENANT=tenant-id
EIP_PR_GUARDIAN_PRINCIPAL_GROUPS=engineering,platform
```

Partial Company Brain configuration fails startup. These group identities are the service identity
used for ACL-trimmed retrieval, not a claim that every GitHub actor can access the source material.
The webhook remains shadow-only and publishes a neutral GitHub check.

## Feedback and promotion boundary

The source contract can retain explicit reviewer labels and independently correlated outcomes as
typed records. The shadow-report and promotion-review contracts additionally bind feedback metrics
to canonical outcome-export and report digests before a human evidence review. They remain
non-authorizing: no source record, report, or packet changes product mode or a merge decision.

The next increment is operational proof: a named pilot must retain those records externally and
demonstrate reviewer and independent post-merge outcomes before any policy promotion is considered.
