# Architecture Decision Records

ADRs capture decisions that constrain the Engineering Intelligence Platform. Use short, immutable records; supersede old decisions rather than silently rewriting history.

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

## Naming

Use `NNNN-short-decision-title.md`, e.g. `0001-llm-not-authorization-boundary.md`.
