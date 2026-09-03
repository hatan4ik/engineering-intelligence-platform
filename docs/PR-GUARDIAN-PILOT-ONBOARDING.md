# PR Guardian Shadow-Pilot Onboarding

| | |
|---|---|
| **Classification** | Reference contract — onboarding only; no named pilot or evidence record is checked into this repository |
| **Runtime boundary** | [`PR-GUARDIAN-REPOSITORY-CONFIG.md`](PR-GUARDIAN-REPOSITORY-CONFIG.md) |
| **Operating runbook** | [`PR-GUARDIAN-SHADOW-PILOT.md`](PR-GUARDIAN-SHADOW-PILOT.md) |
| **Evidence standard** | [`PRODUCTION-EVIDENCE.md`](PRODUCTION-EVIDENCE.md) |

## Purpose

A target repository may keep a reviewed manifest at
`.eip/pr-guardian-shadow-pilot.json`. The manifest is an onboarding record for
one **named, L0/L1 shadow** scope. It describes the actual accountable people,
least-privilege workflow controls, evidence-retention destination, and paired
runtime configuration. It is intentionally not a workflow switch, a GitHub
settings API client, an approval, or production evidence.

The checked-in parser and validator live in
[`product/pr_guardian/pilot.py`](../product/pr_guardian/pilot.py) and
[`scripts/validate_pr_guardian_shadow_pilot.py`](../scripts/validate_pr_guardian_shadow_pilot.py).
They reject advisory/enforcement mode, a required check, PR-head execution in a
trusted workflow, a write-capable evaluator, placeholders in accountable
identities, and Actions artifacts as the sole evidence destination.

## Required target-repository record

Create the manifest in the **target pilot repository**, not in this reference
implementation. It must have exactly these fields:

```json
{
  "schema_version": 1,
  "pilot_id": "pr-guardian-<real-scope>",
  "repository": "<owner>/<repository>",
  "service_ids": ["<service-id>"],
  "owner_ids": ["<accountable-team-or-owner>"],
  "evidence_sources": ["github-pull-request"],
  "policy_version": "<reviewed-policy-version>",
  "data_classification": "internal",
  "mode": "shadow",
  "decision_impact": "advisory",
  "configuration_path": ".eip/pr-guardian.json",
  "minimum_shadow_observations": 30,
  "reviewer_labels": {
    "confirmed_risk": "eip-pr-guardian/confirmed-risk",
    "false_positive": "eip-pr-guardian/false-positive",
    "useful": "eip-pr-guardian/useful",
    "not_useful": "eip-pr-guardian/not-useful"
  },
  "workflow_controls": {
    "evaluation_permissions": ["contents:read", "pull-requests:read"],
    "publisher_permissions": ["actions:read", "checks:write", "contents:read", "issues:write", "pull-requests:write"],
    "outcome_permissions": ["contents:read", "issues:write", "pull-requests:read"],
    "report_permissions": ["actions:read", "contents:read"],
    "evaluation_has_write_token": false,
    "publisher_checks_out_pr_head": false,
    "outcome_checks_out_pr_head": false,
    "check_is_required": false
  },
  "kill_switch_variable": "EIP_PR_GUARDIAN_KILL_SWITCH",
  "kill_switch_engaged_value": "true",
  "evidence_retention": {
    "system": "<approved-external-evidence-system>",
    "locator": "<immutable-scope-locator>",
    "retention_days": 90,
    "access_control_ref": "<access-control-reference>",
    "immutability_control_ref": "<immutability-control-reference>"
  },
  "operating_model": {
    "pilot_owner": "<actual-pilot-owner>",
    "security_reviewer": "<actual-security-reviewer>",
    "developer_experience_owner": "<actual-dx-owner>",
    "reviewer_disposition_sla_hours": 72,
    "hypercare_days": 14
  }
}
```

Angle-bracketed values are deliberately invalid placeholders. Replace them with
approved, real values in the target repository before validation; do not copy
this example as an operating record. Names in a manifest describe ownership and
review handoffs only. They do not constitute approval.

## Operator sequence

1. Obtain the target service owner's consent, Security review, Developer
   Experience owner, data classification, and an approved external immutable
   evidence destination. This repository cannot supply or infer any of them.
2. Create the exact four GitHub labels and configure the kill-switch variable
   according to the shadow-pilot runbook. Keep the neutral shadow check out of
   required branch protection/rulesets.
3. Set the target repository's `.eip/pr-guardian.json` to `"mode": "shadow"`
   with the same repository, service, owner, evidence-source, and policy values
   as the manifest.
4. Validate the record from a trusted checkout of this implementation:

   ```bash
   PYTHONPATH=. python scripts/validate_pr_guardian_shadow_pilot.py \
     --manifest /path/to/target/.eip/pr-guardian-shadow-pilot.json \
     --config-root /path/to/target
   ```

5. Have the responsible humans review the result, then use the operating
   runbook to enable shadow observation. Retain the resulting data externally;
   the validator neither invokes GitHub nor creates evidence.

## What remains outside this contract

The contract cannot prove GitHub settings, collaborator permissions, label
creation, a live workflow run, reviewer disposition, evidence export,
independent post-merge correlation, or a promotion decision. Those are
external operational facts and remain **not proven** until retained under the
production-evidence contract. Reaching the 30-observation minimum does not
authorize advisory publishing, a required check, or enforcement.
