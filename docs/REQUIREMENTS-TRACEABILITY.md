# Requirements and Evidence Traceability

| | |
|---|---|
| **Status** | Current requirements baseline; operational evidence is explicitly tracked, not implied |
| **Authoritative source** | [`../requirements/baseline.json`](../requirements/baseline.json) |
| **Validation** | `python scripts/verify_requirements_baseline.py --check-rendered` |
| **Evidence registry** | [`PRODUCTION-EVIDENCE.md`](PRODUCTION-EVIDENCE.md) |
| **Design baseline** | [`../architecture/non-functional-requirements.md`](../architecture/non-functional-requirements.md) |

## Purpose

This is the Company Brain's requirements-to-design-to-test index. The JSON
baseline is authoritative; this view is checked in CI and exists so a reviewer
can see implementation status, responsible role, and operational-evidence
state without inferring production proof from a green build.

`reference-implemented` means a repository implementation and automated test
exist. `reference-partial` means a known gap remains. `planned` means no
implementation claim is made. In every case, `not-collected` operational
evidence means the requirement is **not proven for a named live scope**.

## Current baseline

<!-- BEGIN GENERATED REQUIREMENTS TABLE -->
| ID | Criticality | Sensitivity | Impact | Tier | Status | Owner | Evidence |
|---|---|---|---|---|---|---|---|
| EIP-SEC-014 | high | restricted | read-only | L0/L1 | reference-implemented | platform-security | not-collected |
| EIP-DATA-021 | high | restricted | advisory | L0/L1 | reference-implemented | data-governance | not-collected |
| EIP-PRG-001 | high | internal | advisory | L0/L1 | reference-implemented | developer-experience | not-collected |
| EIP-PRG-002 | high | internal | advisory | L0/L1 | reference-implemented | developer-experience | not-collected |
| EIP-AUD-010 | high | restricted | consequential | L3/L4 | reference-partial | platform-engineering | not-collected |
| EIP-CTRL-018 | critical | restricted | consequential | L3/L4 | reference-partial | sre-platform | not-collected |
| EIP-CTRL-022 | critical | restricted | consequential | L4 | reference-implemented | sre-platform | not-collected |
| EIP-OPS-004 | high | internal | advisory | L2 | reference-implemented | sre-platform | not-collected |
| EIP-GOV-030 | high | restricted | consequential | all | planned | data-governance | not-collected |
| EIP-PERF-040 | medium | internal | advisory | all | planned | platform-engineering | not-collected |
<!-- END GENERATED REQUIREMENTS TABLE -->

## Tiering rule

Every proposed workflow is classified on two independent axes before it uses
real organizational data or receives a higher autonomy level. The stricter
cell controls; an autonomy label never weakens a data or decision control.

| Data sensitivity | Read-only | Advisory / proposal | Consequential action |
|---|---|---|---|
| **Public** | Provenance and source-owner check | Provenance, reviewer-visible uncertainty, and feedback | Not an approved default; classify the action's target data instead |
| **Internal** | Authenticated identity, purpose, retention, and source access checks | Above plus human disposition, cost/latency budget, and owner review | OPA/policy, named service owner, immutable audit, rollback, and independent verification |
| **Restricted** | Authorization before retrieval, least privilege, evidence lineage, audit access policy, and explicit refusal behavior | Above plus human-in-the-loop SLA, escalation, and retained promotion evidence | All internal controls plus certified scope, approval/expiry, kill switch, durable audit/state, drill evidence, and Security/SRE approval |

The requirements baseline records the chosen sensitivity and decision impact
for each current workflow. A new workflow must add a record before its first
real-data or pilot use.

## Audit and evidence lineage contract

For every consequential transition, retain the following fields in the
approved audit/evidence system: correlation ID; principal and authorization
context; evidence IDs, provenance, classification, and limitations; model,
prompt, policy, image, and runbook versions; proposed and executed action;
approval/waiver; verification result; cost/latency; outcome; and immutable
artifact references. Access to that record is itself governed by the same data
classification.

The repository can validate contract shape and reference paths. It cannot
create a real audit export, security review, or pilot outcome. Those records
remain promotion gates in the [production evidence registry](PRODUCTION-EVIDENCE.md).

## Model-approval submission checklist

Before enabling a named pilot or changing model/prompt behavior, attach a
review packet that identifies:

1. the user workflow, repository/service scope, owner, data sensitivity, and decision impact;
2. input sources, authorization mechanism, retention/deletion behavior, and evidence lineage;
3. model/deployment, prompt version, quality/refusal/adversarial evaluation, and known limitations;
4. human handoff, disposition and escalation SLA, operator training, and stop/kill procedure;
5. cost/latency/throughput budget, monitoring, and degradation behavior; and
6. rollback, expiry, approvers, and links to retained evidence in the approved system.

This checklist is a required review artifact, not a claim that Finance, Legal,
Security, or a service owner has already signed off.
