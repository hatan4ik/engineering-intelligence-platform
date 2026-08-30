# Static Analysis and Type-Safety Baseline

| | |
|---|---|
| **Status** | Current implementation-quality contract; it does not prove production behavior or readiness. |
| **Canonical baseline** | [`../requirements/static-analysis-baseline.json`](../requirements/static-analysis-baseline.json) |
| **Tool installation** | [`../requirements/dev.txt`](../requirements/dev.txt) |
| **Related review** | [`reviews/ENGINEERING_REVIEW.md`](reviews/ENGINEERING_REVIEW.md) |

## Purpose

The Company Brain has dynamic integration boundaries by design: webhooks, Azure responses,
configuration, and JSON enter as untrusted data. The goal is not an unrealistic repository-wide
ban on `Any`; it is to narrow data immediately, make public contracts explicit, and prevent
static-analysis debt from growing while the existing code is improved.

The baseline currently covers the product and control-path packages: `app`, `company_brain`,
`intelligence`, `product`, `remediation`, `control_plane`, `state`, and `integrations`. It
intentionally does not claim that every package or external SDK is fully type-checked yet.

## Ratchet

`requirements/static-analysis-baseline.json` pins tool versions, selected package scope, and the
maximum count for each check. The CI command runs Ruff's import/name correctness rules, mypy with
explicit package bases, and an AST-based count of real `Any` uses and `# type: ignore` comments
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
4. Run mypy with `explicit_package_bases` so valid implicit-namespace packages are checked without
   requiring mechanical `__init__.py` marker files.
5. Add stricter Ruff rules, a second type checker, or a wider scope only after measuring their
   starting debt in a separate, reviewable baseline change.

This is a delivery guardrail, not a claim that the initial ceilings represent an acceptable end
state. The next increments are to replace raw report dictionaries with DTOs, remove existing
dynamic paths in public control interfaces, and lower the recorded ceilings in small slices.
