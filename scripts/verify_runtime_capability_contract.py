"""Keep code, chart, Terraform, and current-state claims in one checked contract.

The contract records *reference* capability exposure. It deliberately validates
checked-in sources only: a passing result is not deployment, environment, or
production evidence.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASELINE = ROOT / "requirements" / "runtime-capability-baseline.json"
DEFAULT_DOCUMENT = ROOT / "docs" / "RUNTIME-CAPABILITY-CONTRACT.md"
_ID = re.compile(r"^EIP-RUNTIME-[A-Z0-9-]+$")
_ENV = re.compile(r"^[A-Z][A-Z0-9_]+$")
_CHART_ENV = re.compile(r"^\s*-\s+name:\s+([A-Z][A-Z0-9_]+)\s*$", re.MULTILINE)
_STATES = frozenset(
    {
        "chart-exposed-reference",
        "code-reference-only",
        "process-composed-reference",
    }
)


class RuntimeCapabilityContractError(ValueError):
    """The capability baseline is malformed or refers outside the repository."""


@dataclass(frozen=True)
class MarkerReference:
    path: str
    markers: tuple[str, ...]


@dataclass(frozen=True)
class ChartSurface:
    template: str
    exposes: tuple[str, ...]
    omits: tuple[str, ...]


@dataclass(frozen=True)
class RuntimeCapability:
    capability_id: str
    name: str
    state: str
    evidence_status: str
    code: tuple[MarkerReference, ...]
    chart: ChartSurface
    terraform_markers: tuple[str, ...]
    documentation: tuple[MarkerReference, ...]


@dataclass(frozen=True)
class RuntimeCapabilityBaseline:
    status: str
    capabilities: tuple[RuntimeCapability, ...]


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise RuntimeCapabilityContractError(f"{label} must be an object")
    return value


def _text(value: object, label: str, *, maximum: int = 500) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise RuntimeCapabilityContractError(f"{label} must be non-blank text")
    return value.strip()


def _strings(value: object, label: str, *, allow_empty: bool = False) -> tuple[str, ...]:
    if not isinstance(value, list) or (not value and not allow_empty):
        raise RuntimeCapabilityContractError(f"{label} must be " + ("a list" if allow_empty else "a non-empty list"))
    items = tuple(_text(item, f"{label} entry") for item in value)
    if len(items) != len(set(items)):
        raise RuntimeCapabilityContractError(f"{label} entries must be unique")
    return items


def _marker_references(value: object, label: str) -> tuple[MarkerReference, ...]:
    if not isinstance(value, list) or not value:
        raise RuntimeCapabilityContractError(f"{label} must be a non-empty list")
    references: list[MarkerReference] = []
    for index, raw in enumerate(value):
        item = _mapping(raw, f"{label}[{index}]")
        if set(item) != {"path", "markers"}:
            raise RuntimeCapabilityContractError(f"{label}[{index}] must contain only path and markers")
        references.append(
            MarkerReference(
                path=_text(item["path"], f"{label}[{index}].path"),
                markers=_strings(item["markers"], f"{label}[{index}].markers"),
            )
        )
    if len({item.path for item in references}) != len(references):
        raise RuntimeCapabilityContractError(f"{label} paths must be unique")
    return tuple(references)


def _chart_surface(value: object, label: str) -> ChartSurface:
    item = _mapping(value, label)
    if set(item) != {"template", "exposes", "omits"}:
        raise RuntimeCapabilityContractError(f"{label} must contain only template, exposes, and omits")
    surface = ChartSurface(
        template=_text(item["template"], f"{label}.template"),
        exposes=_strings(item["exposes"], f"{label}.exposes", allow_empty=True),
        omits=_strings(item["omits"], f"{label}.omits", allow_empty=True),
    )
    environment_names = (*surface.exposes, *surface.omits)
    if any(not _ENV.fullmatch(name) for name in environment_names):
        raise RuntimeCapabilityContractError(f"{label} environment names must be uppercase identifiers")
    if set(surface.exposes).intersection(surface.omits):
        raise RuntimeCapabilityContractError(f"{label} cannot expose and omit the same environment variable")
    return surface


def load_baseline(path: Path = DEFAULT_BASELINE) -> RuntimeCapabilityBaseline:
    """Load the explicit source-only capability baseline."""

    try:
        payload: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeCapabilityContractError(f"cannot read runtime capability baseline {path}: {error}") from error
    root = _mapping(payload, "runtime capability baseline")
    if set(root) != {"schema_version", "status", "capabilities"}:
        raise RuntimeCapabilityContractError("runtime capability baseline must contain schema_version, status, and capabilities")
    if root["schema_version"] != 1:
        raise RuntimeCapabilityContractError("runtime capability baseline.schema_version must be 1")
    status = _text(root["status"], "runtime capability baseline.status")
    if status != "reference-only":
        raise RuntimeCapabilityContractError("runtime capability baseline.status must be reference-only")
    raw_capabilities = root["capabilities"]
    if not isinstance(raw_capabilities, list) or not raw_capabilities:
        raise RuntimeCapabilityContractError("runtime capability baseline.capabilities must be a non-empty list")
    capabilities: list[RuntimeCapability] = []
    for index, raw in enumerate(raw_capabilities):
        item = _mapping(raw, f"capabilities[{index}]")
        expected = {
            "id",
            "name",
            "state",
            "evidence_status",
            "code",
            "chart",
            "terraform_markers",
            "documentation",
        }
        if set(item) != expected:
            raise RuntimeCapabilityContractError(f"capabilities[{index}] has unexpected or missing fields")
        capability_id = _text(item["id"], f"capabilities[{index}].id", maximum=120)
        if not _ID.fullmatch(capability_id):
            raise RuntimeCapabilityContractError(f"capabilities[{index}].id is invalid")
        state = _text(item["state"], f"capabilities[{index}].state", maximum=80)
        if state not in _STATES:
            raise RuntimeCapabilityContractError(f"capabilities[{index}].state is invalid")
        evidence_status = _text(item["evidence_status"], f"capabilities[{index}].evidence_status", maximum=80)
        if evidence_status != "not-collected":
            raise RuntimeCapabilityContractError(
                f"capabilities[{index}].evidence_status must be not-collected in this source-only baseline"
            )
        chart = _chart_surface(item["chart"], f"capabilities[{index}].chart")
        if state == "chart-exposed-reference" and not chart.exposes:
            raise RuntimeCapabilityContractError(f"capabilities[{index}] chart-exposed-reference needs chart.exposes")
        if state == "code-reference-only" and (chart.exposes or not chart.omits):
            raise RuntimeCapabilityContractError(
                f"capabilities[{index}] code-reference-only must name omitted chart variables only"
            )
        if state == "process-composed-reference" and (chart.exposes or chart.omits):
            raise RuntimeCapabilityContractError(
                f"capabilities[{index}] process-composed-reference cannot declare chart variables"
            )
        capabilities.append(
            RuntimeCapability(
                capability_id=capability_id,
                name=_text(item["name"], f"capabilities[{index}].name", maximum=160),
                state=state,
                evidence_status=evidence_status,
                code=_marker_references(item["code"], f"capabilities[{index}].code"),
                chart=chart,
                terraform_markers=_strings(
                    item["terraform_markers"], f"capabilities[{index}].terraform_markers", allow_empty=True
                ),
                documentation=_marker_references(
                    item["documentation"], f"capabilities[{index}].documentation"
                ),
            )
        )
    ids = [item.capability_id for item in capabilities]
    if len(ids) != len(set(ids)):
        raise RuntimeCapabilityContractError("runtime capability baseline IDs must be unique")
    return RuntimeCapabilityBaseline(status=status, capabilities=tuple(capabilities))


def _repository_file(root: Path, relative: str, label: str) -> Path:
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError as error:
        raise RuntimeCapabilityContractError(f"{label} escapes the repository: {relative}") from error
    if not candidate.is_file():
        raise RuntimeCapabilityContractError(f"{label} is missing: {relative}")
    return candidate


def _markers_present(root: Path, reference: MarkerReference, label: str) -> list[str]:
    try:
        content = _repository_file(root, reference.path, label).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        return [f"{label}: cannot read {reference.path}: {error}"]
    return [f"{label}: {reference.path} is missing marker {marker!r}" for marker in reference.markers if marker not in content]


def verify_baseline(baseline: RuntimeCapabilityBaseline, *, root: Path = ROOT) -> tuple[str, ...]:
    """Return every source/configuration mismatch without implying deployment proof."""

    errors: list[str] = []
    terraform_files = sorted((root / "infra" / "terraform").glob("*.tf"))
    terraform = "\n".join(path.read_text(encoding="utf-8") for path in terraform_files)
    for capability in baseline.capabilities:
        label = capability.capability_id
        for reference in capability.code:
            errors.extend(_markers_present(root, reference, f"{label} code"))
        try:
            chart = _repository_file(root, capability.chart.template, f"{label} chart").read_text(encoding="utf-8")
        except (RuntimeCapabilityContractError, OSError, UnicodeDecodeError) as error:
            errors.append(str(error))
            chart = ""
        chart_environment = set(_CHART_ENV.findall(chart))
        for variable in capability.chart.exposes:
            if variable not in chart_environment:
                errors.append(f"{label} chart must expose {variable} in {capability.chart.template}")
        for variable in capability.chart.omits:
            if variable in chart_environment:
                errors.append(f"{label} chart must not expose {variable} in {capability.chart.template}")
        for marker in capability.terraform_markers:
            if marker not in terraform:
                errors.append(f"{label} Terraform support is missing marker {marker!r}")
        for reference in capability.documentation:
            errors.extend(_markers_present(root, reference, f"{label} documentation"))
    return tuple(errors)


def render_markdown(baseline: RuntimeCapabilityBaseline) -> str:
    """Render the compact capability overview embedded in the documentation."""

    rows = [
        "| ID | Capability | Source state | Chart surface | Terraform support | Evidence |",
        "|---|---|---|---|---|---|",
    ]
    for capability in baseline.capabilities:
        if capability.chart.exposes:
            chart = "exposes " + ", ".join(f"`{item}`" for item in capability.chart.exposes)
        elif capability.chart.omits:
            chart = "intentionally omits " + ", ".join(
                f"`{item}`" for item in capability.chart.omits
            )
        else:
            chart = "no chart configuration"
        terraform = ", ".join(f"`{item}`" for item in capability.terraform_markers) or "none declared"
        rows.append(
            f"| {capability.capability_id} | {capability.name} | {capability.state} | {chart} | {terraform} | {capability.evidence_status} |"
        )
    return "\n".join(rows)


def rendered_document_matches(path: Path, baseline: RuntimeCapabilityBaseline) -> bool:
    """Return whether the checked-in Markdown overview matches the source baseline."""

    try:
        document = path.read_text(encoding="utf-8")
    except OSError:
        return False
    start = "<!-- BEGIN GENERATED RUNTIME CAPABILITY TABLE -->"
    end = "<!-- END GENERATED RUNTIME CAPABILITY TABLE -->"
    if start not in document or end not in document:
        return False
    actual = document.split(start, 1)[1].split(end, 1)[0].strip()
    return actual == render_markdown(baseline)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--document", type=Path, default=DEFAULT_DOCUMENT)
    parser.add_argument("--check-rendered", action="store_true")
    parser.add_argument("--print-rendered", action="store_true")
    args = parser.parse_args(argv)
    try:
        baseline = load_baseline(args.baseline)
        errors = list(verify_baseline(baseline))
    except RuntimeCapabilityContractError as error:
        errors = [str(error)]
        baseline = None
    if baseline is not None and args.check_rendered and not rendered_document_matches(args.document, baseline):
        errors.append(
            f"rendered runtime capability table in {args.document} is stale; run "
            "python scripts/verify_runtime_capability_contract.py --print-rendered"
        )
    if errors:
        print("runtime capability contract failed:", file=sys.stderr)
        print("\n".join(f"- {error}" for error in errors), file=sys.stderr)
        return 1
    assert baseline is not None
    if args.print_rendered:
        print(render_markdown(baseline))
    else:
        print(
            f"runtime capability contract verified: {len(baseline.capabilities)} reference capabilities; "
            "no deployment evidence implied"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
