# Static Analysis and Type-Safety Baseline

| | |
|---|---|
| **Classification** | Reference quality contract — it does not prove production behavior or readiness |
| **Canonical baseline** | [`../requirements/static-analysis-baseline.json`](../requirements/static-analysis-baseline.json) |
| **Tool installation** | [`../requirements/dev.txt`](../requirements/dev.txt) |
| **Related review** | [`reviews/ENGINEERING_REVIEW.md`](reviews/ENGINEERING_REVIEW.md) |

## Purpose

The Company Brain has dynamic integration boundaries by design: webhooks, Azure responses,
configuration, and JSON enter as untrusted data. The delivery code narrows those inputs at the
boundary, makes public contracts explicit, and forbids active `Any` annotations and type-ignore
suppression in the packaged product surface.

The baseline covers every distributable product package declared in `pyproject.toml`: `app`,
`company_brain`, `control_plane`, `feedback`, `finops`, `ingestion`, `integrations`,
`intelligence`, `orchestration`, `portal`, `product`, `remediation`, `resilience`, `security`,
`state`, `telemetry`, and `topology`. It deliberately does not count third-party SDK stubs,
tests, or developer/CI tools as proof that those separate surfaces are fully strict.

## Ratchet

`requirements/static-analysis-baseline.json` pins tool versions, selected package scope, and the
maximum count for each check. The CI command runs Ruff's import/name correctness rules, mypy with
explicit package bases and unused-ignore warnings, and an AST-based count of real `Any` uses and `# type: ignore` comments
(not prose, strings, or an unused import). A change may reduce a ceiling only together with its observed result; it may never
raise one casually.

```bash
pip install -r app/requirements.txt -r requirements/dev.txt
PYTHONPATH=. python scripts/verify_static_analysis_baseline.py
```

The checker exits `0` when all counts are at or below their ceilings, `1` for a regression, and
`2` when a tool/configuration is unusable. It does not suppress a failure or manufacture an
operational evidence record.

## Working rule

1. At an external boundary, parse JSON into a Pydantic model, `TypedDict`, or small normalizer as
   soon as possible; use `Mapping[str, object]` only until that narrowing occurs.
2. Public product/policy/adaptor interfaces must state input and output types. Expected product
   outcomes should use explicit result models or discriminated states, not open dictionary shapes.
3. A new `Any` or `# type: ignore` in the scoped packages is a ratchet regression. Eliminate it,
   narrow it at the boundary, or make a separately reviewed baseline reduction/exception decision.
4. Run mypy with `explicit_package_bases` and `warn_unused_ignores` so valid implicit-namespace
   packages are checked without requiring mechanical `__init__.py` marker files and stale suppressions fail.
5. Add stricter Ruff rules, a second type checker, or a wider scope only after measuring their
   starting debt in a separate, reviewable baseline change.

The current checked-in ceilings are zero for Ruff diagnostics, mypy errors, active `Any`
references, and type-ignore comments in this product surface. The next increment is not to
relax those ceilings; it is to add stricter rules and supporting-tool scope only with their own
measured, reviewable baseline.
