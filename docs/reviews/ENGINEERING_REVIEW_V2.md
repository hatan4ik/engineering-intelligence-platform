# Engineering Review — Company Brain (V2: post-quality-wave correction)

| | |
|---|---|
| **Classification** | Current implementation review addendum |
| **Owner** | Platform Engineering |
| **Baseline reviewed** | `origin/main` at `c52f344` (2026-08-30) |
| **Canonical review** | [Engineering Review](ENGINEERING_REVIEW.md) — historical baseline, findings, and dated reconciliation |
| **Authoritative current state** | [Current Position](../CURRENT-POSITION.md) |
| **Verification** | [Reference Implementation CI run 33302171993](https://github.com/hatan4ik/engineering-intelligence-platform/actions/runs/33302171993) succeeded for this baseline |
| **Evidence rule** | Source and CI establish reference behavior only; they do not establish a named pilot, deployed runtime, production readiness, or autonomy certification. |

## Executive assessment

The P0/P1 quality wave materially improved the Company Brain reference implementation: PR Guardian
now has cohesive pipeline components, operational intelligence has typed ingress and presentation
boundaries, package inventory is checked against the distributable, and the static-analysis debt is
an explicit non-increasing contract. Those are real engineering improvements.

They do **not** make the platform complete or production-proven. Company Brain remains at Stage 0
until PR Guardian has a named shadow pilot, retained human outcomes, and the product strategy's
measured promotion evidence. This addendum deliberately does not assign a second numeric scorecard:
the canonical review's ratings are historical, and a credible new score would require a full
independent assessment rather than an assertion made by the implementation change itself.

## Corrections to the unmerged V2 draft

| Draft claim | Evidence-backed correction |
|---|---|
| PR Guardian and operations are “entirely” or “strictly” isolated. | The decomposition is a meaningful source-level improvement: `product/pr_guardian/review_pipeline.py` and `app/operations/` separate responsibilities, while `app/application.py` remains the explicit composition root. It is reference-tested, not proof of a complete architecture or external delivery path. |
| Missing `__init__.py` files were fixed to define package boundaries. | The repository intentionally uses implicit namespace packages. `pyproject.toml` sets `namespaces = true`, and package-inventory tests verify the release inventory; marker files should not be added mechanically. |
| Packaging is fully deterministic. | The source contract now pins and installs the build backend for the intentionally non-isolated wheel check, and CI verifies wheel/image/import closure. That is artifact consistency, not a deployed-release or supply-chain certification claim. |
| Runtime safety and Temporal resilience are proven. | Kill switches, fail-closed startup, policy checks, and bounded workflows are source contracts. No named environment, managed Temporal exercise, retained drill, or production evidence exists. |
| Typing is “flawless” and external dictionaries are eradicated. | External event and response DTOs are materially improved, including the L2 `requires_human: Literal[True]` invariant. The current ratchet still permits 36 mypy diagnostics, 21 `Any` references, and one `# type: ignore` in its defined core scope. |
| A 9+/10 maturity rating follows from the refactor. | Refactoring improves maintainability but does not substitute for product evidence. The authoritative state remains a CI-validated reference implementation with no pilot exit beyond Stage 0. |

## Confirmed improvements

| Area | Current source evidence | Limit of the claim |
|---|---|---|
| PR Guardian composition | `product/pr_guardian_service.py` delegates to `review_pipeline.py`, `finding_factory.py`, `publication.py`, and `telemetry.py`. | Component boundaries are testable; usefulness and calibration remain unproven outside a pilot. |
| Operational ingress | `app/operations/contracts.py`, `routes.py`, `presentation.py`, and `app/application.py` use typed request/response records and explicit composition. | The Azure Monitor/ADO delivery path has no retained external-event evidence. |
| Human-only L2 proposals | `product/l2_proposals.py` and `app/operations/contracts.py` encode `requires_human: Literal[True]`; endpoint tests pin non-execution. | It is a proposal boundary, not authorization or autonomous execution. |
| Package truth | `pyproject.toml`, `requirements/build.txt`, and `scripts/verify_package_inventory.py` check an exact build backend plus wheel/image/import inventory. | A passing build validates the repository artifact, not an environment deployment. |
| Type and trace discipline | `app/settings.py`, `control_plane/correlation.py`, and `requirements/static-analysis-baseline.json` make settings, correlation, and debt budgets explicit. | The recorded type-debt ceiling is a ratchet, not an end-state quality claim. |
| Shared Company Brain vocabulary | `company_brain/product_contracts.py` defines product-neutral Evidence, Finding, Outcome, and provenance records. | Reuse is only demonstrated by PR Guardian until a second product adopts the contract. |

## Evidence still required

1. Name one or two pilot repositories and service owners, then retain shadow observations and every
   reviewer disposition according to the [PR Guardian shadow-pilot runbook](../PR-GUARDIAN-SHADOW-PILOT.md).
2. Resolve and verify least-privilege result retention on a real closed pull request. The most recent
   [publisher run](https://github.com/hatan4ik/engineering-intelligence-platform/actions/runs/33302281840)
   correctly refused a missing evaluation artifact and published neutral, but it is not pilot evidence.
3. Earn the advisory gate with measured precision, recall, acceptance, latency, cost, ACL isolation,
   provenance, and a retained promotion packet; do not use a refactor or a score as a substitute.
4. Keep L3/L4 work behind the existing scoped certification, rehearsal, and independent-evidence
   requirements in [Current Position](../CURRENT-POSITION.md) and the [production-evidence registry](../PRODUCTION-EVIDENCE.md).

## Decision

The next product milestone remains a trustworthy PR Guardian shadow pilot, not broader platform
surface area or autonomous remediation. This document corrects an inaccurate draft; it does not
advance a roadmap stage or authorize enforcement.
