# Architecture Decision Records

| | |
|---|---|
| **Classification** | Current design |
| **Owner** | Platform Engineering |
| **Reviewed** | 2026-09-03 |
| **Assertions are** | index of decision records |
| **Authoritative current state** | [`CURRENT-POSITION.md`](../../docs/CURRENT-POSITION.md) |


ADRs capture decisions that constrain the Company Brain architecture. Use short, immutable
records; supersede old decisions rather than silently rewriting history.

## Required sections

- Status: proposed / accepted / deprecated / superseded
- Context
- Decision
- Alternatives considered
- Security and privacy impact
- Reliability and rollback impact
- FinOps impact
- Consequences
- Evidence / metrics that can cause reconsideration

## Initial decision set

1. **LLM is not an authorization boundary.** Deterministic identity, ACL and policy controls authorize access/actions.
2. **Retrieval security trimming occurs before synthesis.** Unauthorized evidence must never enter model context.
3. **Production mutation uses allow-listed deterministic runbooks.** Models may diagnose/plan but do not invent shell commands for autonomous execution.
4. **Every action is verified.** Failed verification triggers rollback or escalation.
5. **Autonomy is service-scoped.** A service must be certified for a specific autonomy level and action catalog.
6. **Azure is the reference implementation, not the domain contract.** Provider adapters isolate cloud-specific APIs.
7. **Offline deterministic mode remains first-class.** CI and core safety tests cannot require live model/cloud credentials.

## Recorded decisions

- [ADR-001: Temporal with private PostgreSQL](001-temporal-control-plane.md)
  defines the target durable workflow engine and its independent persistence.
- [ADR-002: Prompt injection guardrails and semantic cache lifecycle](002-prompt-injection-and-caching.md)
  is a proposed RAG security/caching decision; it is not implementation evidence.
- [ADR-003: Company Brain systems of record and recovery boundaries](003-company-brain-runtime-topology-and-recovery.md)
  assigns canonical state, rebuildable projections, workflow history, audit
  evidence, and broker ownership before a durable runtime is built.

## Naming

Use `NNN-short-decision-title.md`, e.g. `001-llm-not-authorization-boundary.md`.
