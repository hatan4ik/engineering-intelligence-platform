# Targeted Mutation Contract

| | |
|---|---|
| **Status** | Current implementation-quality contract; source-level evidence only |
| **Owner** | Platform Engineering |
| **Command** | `python scripts/verify_targeted_mutations.py` |
| **Scope** | `resilience/dependencies.py` and `tests/test_dependency_boundary.py` |

## Purpose

The Company Brain must refuse unsafe work when an external dependency is saturated or
unhealthy. Line coverage alone cannot demonstrate that the boundary tests would detect
an inverted comparison or removed refusal. This contract mutates four reviewed
`DependencyBoundary` decisions and requires the existing focused test corpus to kill
each mutant.

| Mutation | Required invariant |
|---|---|
| `opens-at-failure-threshold` | The circuit opens on its configured transient-failure threshold. |
| `rejects-open-circuit` | A circuit remains closed to calls until the recovery window expires. |
| `rejects-bulkhead-overflow` | A full bulkhead refuses another in-flight call. |
| `preserves-open-circuit-from-stale-success` | A late success cannot erase a circuit opened by another request. |

## How the gate works

The verifier first runs an unmodified copy of the focused test file. For each mutation,
it copies the `resilience` package and the test file into a temporary directory,
applies exactly one syntactically valid source mutation to the copy, and runs `pytest`
against that copy. A mutant is counted as killed only when pytest reports a test failure
(exit `1`). A collection error, tool error, or a passing mutant fails the gate. The
working tree is never modified by the verifier.

The repository’s CI runs this command after the normal test suite. The small unit test
for the verifier checks that every mutation still has exactly one source target and
compiles before CI spends time executing nested test processes.

## Evidence boundary

This is **not** a claim of 100% mutation coverage, repository-wide mutation testing,
or production resilience. It is a repeatable source-level test of four named control
invariants. It does not exercise GitHub, OPA, Azure, Kubernetes, Temporal, network
timeouts, or deployed telemetry.

`mutmut` was evaluated for broader mutation testing but is not declared as a project
dependency: in the supported local Python environment its required `libcst` dependency
could not be built without a Rust compiler. A dependency declaration that cannot run in
the supported toolchain would not be a real CI gate. Broader mutation coverage should
be added only when its toolchain is reproducibly available and its targets, thresholds,
and evidence limits are separately reviewed.

## Extension rule

Add another mutation only for a high-risk invariant with a focused deterministic test
corpus. Keep the mutation and its test target explicit, run an unmutated baseline first,
and record the new scope here. Do not turn a surviving mutant into a baseline allowance.
