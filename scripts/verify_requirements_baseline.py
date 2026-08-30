"""Validate the Company Brain requirements-to-evidence baseline.

The JSON file is the authoritative record. This tool validates its schema and
repository references and can ensure the concise Markdown rendering committed
for reviewers is derived from the same source.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Final, Mapping, Sequence


ROOT: Final[Path] = Path(__file__).resolve().parents[1]
DEFAULT_BASELINE: Final[Path] = ROOT / "requirements" / "baseline.json"
DEFAULT_VIEW: Final[Path] = ROOT / "docs" / "REQUIREMENTS-TRACEABILITY.md"
_CRITICALITIES = frozenset({"critical", "high", "medium", "low"})
_SENSITIVITIES = frozenset({"public", "internal", "restricted"})
_IMPACTS = frozenset({"read-only", "advisory", "consequential"})
_AUTONOMY = frozenset({"reference", "L0/L1", "L2", "L3/L4", "L4", "all"})
_STATUSES = frozenset({"reference-implemented", "reference-partial", "planned"})
_EVIDENCE_STATUSES = frozenset({"not-collected", "collected", "not-applicable"})
_REQUIRED_FIELDS = frozenset(
    {
        "id",
        "statement",
        "criticality",
        "data_sensitivity",
        "decision_impact",
        "autonomy_tier",
        "implementation_status",
        "design_refs",
        "implemented_by",
        "verified_by",
        "operational_evidence",
        "owner",
        "review_cycle_days",
    }
)


def load_baseline(path: Path = DEFAULT_BASELINE) -> list[dict[str, object]]:
    """Load the authoritative requirements document without coercing its fields."""

    try:
        payload: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read requirements baseline {path}: {exc}") from exc
    if not isinstance(payload, Mapping) or payload.get("schema_version") != 1:
        raise ValueError("requirements baseline must be a schema_version 1 object")
    requirements = payload.get("requirements")
    if not isinstance(requirements, list):
        raise ValueError("requirements baseline must contain a requirements list")
    if not all(isinstance(item, Mapping) for item in requirements):
        raise ValueError("each requirement must be an object")
    return [dict(item) for item in requirements]


def validate_baseline(
    requirements: Sequence[Mapping[str, object]],
    *,
    root: Path = ROOT,
) -> list[str]:
    """Return all schema, ownership, and repository-reference errors."""

    errors: list[str] = []
    identifiers: set[str] = set()
    for index, requirement in enumerate(requirements, start=1):
        label = f"requirements[{index}]"
        missing = sorted(_REQUIRED_FIELDS - set(requirement))
        unknown = sorted(set(requirement) - _REQUIRED_FIELDS)
        if missing:
            errors.append(f"{label}: missing fields: {', '.join(missing)}")
        if unknown:
            errors.append(f"{label}: unknown fields: {', '.join(unknown)}")
        identifier = _nonempty_text(requirement.get("id"))
        if identifier is None:
            errors.append(f"{label}: id must be non-empty text")
        elif identifier in identifiers:
            errors.append(f"{label}: duplicate id {identifier}")
        else:
            identifiers.add(identifier)
        _one_of(errors, label, "criticality", requirement.get("criticality"), _CRITICALITIES)
        _one_of(errors, label, "data_sensitivity", requirement.get("data_sensitivity"), _SENSITIVITIES)
        _one_of(errors, label, "decision_impact", requirement.get("decision_impact"), _IMPACTS)
        _one_of(errors, label, "autonomy_tier", requirement.get("autonomy_tier"), _AUTONOMY)
        status = requirement.get("implementation_status")
        _one_of(errors, label, "implementation_status", status, _STATUSES)
        if _nonempty_text(requirement.get("statement")) is None:
            errors.append(f"{label}: statement must be non-empty text")
        if _nonempty_text(requirement.get("owner")) is None:
            errors.append(f"{label}: owner must be non-empty text")
        days = requirement.get("review_cycle_days")
        if type(days) is not int or not 1 <= days <= 365:
            errors.append(f"{label}: review_cycle_days must be an integer from 1 to 365")
        for field in ("design_refs", "implemented_by", "verified_by"):
            values = requirement.get(field)
            if not isinstance(values, list) or not all(_nonempty_text(value) for value in values):
                errors.append(f"{label}: {field} must be a list of non-empty relative paths")
                continue
            for value in values:
                assert isinstance(value, str)
                if not _repository_path(root, value).is_file():
                    errors.append(f"{label}: {field} references missing file {value}")
        if status != "planned":
            for field in ("implemented_by", "verified_by"):
                if not requirement.get(field):
                    errors.append(f"{label}: {field} must not be empty when {status}")
        _validate_operational_evidence(errors, label, requirement.get("operational_evidence"), root)
        if (
            requirement.get("decision_impact") == "consequential"
            and requirement.get("autonomy_tier") not in {"L3/L4", "L4", "all"}
        ):
            errors.append(f"{label}: consequential work must name an L3/L4, L4, or all autonomy tier")
    return errors


def render_markdown(requirements: Sequence[Mapping[str, object]]) -> str:
    """Render the short review table that is embedded in the Markdown view."""

    rows = [
        "| ID | Criticality | Sensitivity | Impact | Tier | Status | Owner | Evidence |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for requirement in requirements:
        evidence = requirement["operational_evidence"]
        assert isinstance(evidence, Mapping)
        rows.append(
            "| {id} | {criticality} | {sensitivity} | {impact} | {tier} | {status} | {owner} | {evidence} |".format(
                id=requirement["id"],
                criticality=requirement["criticality"],
                sensitivity=requirement["data_sensitivity"],
                impact=requirement["decision_impact"],
                tier=requirement["autonomy_tier"],
                status=requirement["implementation_status"],
                owner=requirement["owner"],
                evidence=evidence["status"],
            )
        )
    return "\n".join(rows)


def check_rendered_view(view: Path, requirements: Sequence[Mapping[str, object]]) -> str | None:
    """Return an actionable error when the committed review table is stale."""

    try:
        rendered = view.read_text(encoding="utf-8")
    except OSError as exc:
        return f"cannot read requirements traceability view {view}: {exc}"
    start = "<!-- BEGIN GENERATED REQUIREMENTS TABLE -->"
    end = "<!-- END GENERATED REQUIREMENTS TABLE -->"
    if start not in rendered or end not in rendered:
        return f"{view}: missing generated requirements table markers"
    actual = rendered.split(start, 1)[1].split(end, 1)[0].strip()
    expected = render_markdown(requirements)
    if actual != expected:
        return (
            f"{view}: generated requirements table is stale; run "
            "python scripts/verify_requirements_baseline.py --print-markdown"
        )
    return None


def _repository_path(root: Path, relative: str) -> Path:
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError:
        return root / "__outside_repository__"
    return candidate


def _nonempty_text(value: object) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def _one_of(
    errors: list[str],
    label: str,
    field: str,
    value: object,
    allowed: frozenset[str],
) -> None:
    if value not in allowed:
        errors.append(f"{label}: {field} must be one of {', '.join(sorted(allowed))}")


def _validate_operational_evidence(
    errors: list[str],
    label: str,
    value: object,
    root: Path,
) -> None:
    if not isinstance(value, Mapping):
        errors.append(f"{label}: operational_evidence must be an object")
        return
    required = {"required_for", "status", "registry"}
    if set(value) != required:
        errors.append(f"{label}: operational_evidence must contain only {', '.join(sorted(required))}")
        return
    if _nonempty_text(value.get("required_for")) is None:
        errors.append(f"{label}: operational_evidence.required_for must be non-empty text")
    _one_of(errors, label, "operational_evidence.status", value.get("status"), _EVIDENCE_STATUSES)
    registry = _nonempty_text(value.get("registry"))
    if registry is None or not _repository_path(root, registry).is_file():
        errors.append(f"{label}: operational_evidence.registry must reference a repository file")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--view", type=Path, default=DEFAULT_VIEW)
    parser.add_argument("--check-rendered", action="store_true")
    parser.add_argument("--print-markdown", action="store_true")
    args = parser.parse_args(argv)
    try:
        requirements = load_baseline(args.baseline)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 1
    errors = validate_baseline(requirements)
    if args.check_rendered:
        rendered_error = check_rendered_view(args.view, requirements)
        if rendered_error is not None:
            errors.append(rendered_error)
    if args.print_markdown:
        print(render_markdown(requirements))
    if errors:
        print("requirements baseline validation failed:", file=sys.stderr)
        print("\n".join(f"- {error}" for error in errors), file=sys.stderr)
        return 1
    print(f"requirements baseline verified for {len(requirements)} requirements")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
