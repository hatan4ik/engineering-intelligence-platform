from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Component:
    """A direct, exactly-pinned Python dependency declared by the service."""

    name: str
    version: str


@dataclass(frozen=True)
class ImageEvidence:
    """Evidence produced after scanning the exact local image built in CI.

    This record intentionally is *not* an attestation. It gives reviewers a
    traceable image ID and SBOM digest for the CI run, while admission control
    remains blocked on a registry-backed, signed attestation.
    """

    image_reference: str
    image_id: str
    sbom_sha256: str
    source_revision: str


def normalize_component_name(name: str) -> str:
    """Normalize PyPI names, including requirement extras, for comparison."""

    base = name.split("[", 1)[0].strip()
    return re.sub(r"[-_.]+", "-", base).lower()


def parse_requirements(path: str | Path) -> tuple[Component, ...]:
    """Read direct dependencies and reject anything that is not exactly pinned."""

    components: list[Component] = []
    for raw in Path(path).read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "==" not in line:
            raise ValueError(f"dependency must be exactly pinned: {line}")
        name, version = line.split("==", 1)
        normalized_name = normalize_component_name(name)
        version = version.strip()
        if not normalized_name or not version or ";" in version:
            raise ValueError(f"invalid dependency pin: {line}")
        components.append(Component(name=normalized_name, version=version))
    return tuple(sorted(components, key=lambda component: component.name))


def load_cyclonedx(path: str | Path) -> dict[str, Any]:
    """Load the SBOM format emitted by Syft and reject malformed input."""

    try:
        sbom = json.loads(Path(path).read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"unable to read CycloneDX SBOM: {exc}") from exc
    if not isinstance(sbom, dict):
        raise ValueError("CycloneDX SBOM must be a JSON object")
    return sbom


def verify_image_sbom(
    *,
    sbom: dict[str, Any],
    required_components: tuple[Component, ...],
    image_reference: str,
) -> tuple[bool, tuple[str, ...]]:
    """Fail closed unless a container SBOM contains every direct runtime pin."""

    failures: list[str] = []
    if sbom.get("bomFormat") != "CycloneDX":
        failures.append("SBOM is not CycloneDX")

    metadata = sbom.get("metadata")
    root_component = metadata.get("component") if isinstance(metadata, dict) else None
    if not isinstance(root_component, dict) or root_component.get("type") != "container":
        failures.append("SBOM does not describe a container image")
    else:
        image_name, image_tag = _image_name_and_tag(image_reference)
        if normalize_component_name(str(root_component.get("name", ""))) != image_name:
            failures.append("SBOM container name does not match the built image")
        if image_tag and str(root_component.get("version", "")) != image_tag:
            failures.append("SBOM container tag does not match the built image")

    entries = sbom.get("components")
    if not isinstance(entries, list) or not entries:
        failures.append("SBOM has no components")
        return False, tuple(failures)

    observed: dict[str, set[str]] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        version = entry.get("version")
        if isinstance(name, str) and isinstance(version, str):
            observed.setdefault(normalize_component_name(name), set()).add(version)

    for component in required_components:
        if component.version not in observed.get(component.name, set()):
            failures.append(f"direct dependency missing from image SBOM: {component.name}=={component.version}")
    return not failures, tuple(failures)


def write_image_evidence(
    *,
    output: str | Path,
    image_reference: str,
    image_id: str,
    sbom_path: str | Path,
    source_revision: str,
) -> ImageEvidence:
    """Persist CI evidence without presenting it as a signed provenance claim."""

    if not image_id.startswith("sha256:"):
        raise ValueError("built image ID must be an immutable sha256 value")
    if not source_revision.strip():
        raise ValueError("source revision is required")

    evidence = ImageEvidence(
        image_reference=image_reference,
        image_id=image_id,
        sbom_sha256=_sha256(Path(sbom_path).read_bytes()),
        source_revision=source_revision,
    )
    payload = {
        "schema_version": 1,
        "kind": "local-ci-image-evidence",
        "image": asdict(evidence),
        "limitations": [
            "This record is not a signed provenance attestation.",
            "It must not be used for deployment admission.",
            "Production admission requires a registry-backed signed attestation for the pushed image digest.",
        ],
    }
    Path(output).write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n")
    return evidence


def _image_name_and_tag(image_reference: str) -> tuple[str, str | None]:
    """Return the terminal image name and optional tag for a local Docker ref."""

    reference_without_digest = image_reference.split("@", 1)[0]
    terminal = reference_without_digest.rsplit("/", 1)[-1]
    name, separator, tag = terminal.partition(":")
    return normalize_component_name(name), tag if separator else None


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
