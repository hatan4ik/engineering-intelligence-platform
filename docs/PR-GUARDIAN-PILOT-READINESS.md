# PR Guardian Shadow-Pilot Readiness

| | |
|---|---|
| **Classification** | Operator preflight for a shadow-only target repository |
| **Owner** | Target repository service owner with Platform Engineering |
| **Current stage** | Stage 0 source capability; not a named pilot or operational evidence |
| **Pilot sequence** | [Pilot Onboarding](PR-GUARDIAN-PILOT-ONBOARDING.md) → this preflight → [Shadow Pilot](PR-GUARDIAN-SHADOW-PILOT.md) → [Shadow Report](PR-GUARDIAN-SHADOW-REPORT.md) → [Promotion Review](PR-GUARDIAN-PROMOTION-REVIEW.md) |
| **Evidence standard** | [Production Evidence](PRODUCTION-EVIDENCE.md) |

This is the operator-facing bridge between the checked-in onboarding contracts and a real target-repository pilot. It is deliberately read-only and non-authorizing.

## When to use this document

Use this document after the target repository has a proposed shadow-pilot manifest and runtime
configuration, but before enabling any workflow. A contract-ready result verifies only the
repository-local inputs. It never replaces the external approvals, GitHub settings checks, or
evidence-retention requirements in the rest of the pilot sequence.

Run it against a trusted checkout of the intended target repository:

```bash
PYTHONPATH=. python scripts/pr_guardian_pilot_readiness.py \
  --config-root /path/to/target/repository
```

For automation or an operator portal, request the machine-readable form:

```bash
PYTHONPATH=. python scripts/pr_guardian_pilot_readiness.py \
  --config-root /path/to/target/repository \
  --json
```

The report has only two repository-local states:

- `not-ready` — the shadow manifest/configuration is absent, invalid, or inconsistent.
- `contract-ready` — `.eip/pr-guardian-shadow-pilot.json` is valid and the repository-owned `.eip/pr-guardian.json` matches the exact named shadow scope.

`contract-ready` **does not mean the pilot is active**. The report always leaves the following as external operational work until independently verified:

1. the four reviewer labels and least-privilege workflow permissions exist in the target GitHub repository;
2. the kill switch exists and the neutral shadow check is not required by branch protection/rulesets;
3. the named service owner, Security/SRE reviewer, and Developer Experience owner actually consented to the pilot;
4. the declared external evidence destination exists with the stated access-control, retention, and immutability properties; and
5. a real shadow workflow has run and its first observation has been retained outside transient Actions artifacts.

For that reason every readiness report fixes these fields to false:

```json
{
  "operational_evidence_collected": false,
  "advisory_or_enforcement_authorized": false
}
```

The authoritative manifest shape remains in [PR Guardian Shadow-Pilot Onboarding](PR-GUARDIAN-PILOT-ONBOARDING.md), and the operating/evidence requirements remain in [PR Guardian Shadow Pilot](PR-GUARDIAN-SHADOW-PILOT.md) and [Production Evidence](PRODUCTION-EVIDENCE.md).

The next maturity step after a contract-ready checkout is an explicitly approved, named target repository in shadow mode. No source-only validator can create that operational fact.
