from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Component:
    name: str
    version: str


@dataclass(frozen=True)
class Provenance:
    subject_sha256: str
    sbom_sha256: str
    builder: str
    source_revision: str


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def parse_requirements(path: str | Path) -> tuple[Component, ...]:
    components: list[Component] = []
    for raw in Path(path).read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "==" not in line:
            raise ValueError(f"dependency must be exactly pinned: {line}")
        name, version = line.split("==", 1)
        if not name or not version:
            raise ValueError(f"invalid dependency pin: {line}")
        components.append(Component(name=name, version=version))
    return tuple(sorted(components, key=lambda c: c.name.lower()))


def build_sbom(components: tuple[Component, ...]) -> dict[str, object]:
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "version": 1,
        "components": [
            {"type": "library", "name": c.name, "version": c.version}
            for c in components
        ],
    }


def canonical_json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def issue_provenance(*, subject: bytes, sbom: dict[str, object], builder: str, source_revision: str) -> Provenance:
    return Provenance(
        subject_sha256=_sha256(subject),
        sbom_sha256=_sha256(canonical_json(sbom)),
        builder=builder,
        source_revision=source_revision,
    )


def verify_admission(
    *,
    subject: bytes,
    sbom: dict[str, object],
    provenance: Provenance,
    trusted_builders: tuple[str, ...],
    expected_revision: str,
) -> tuple[bool, str]:
    if provenance.builder not in trusted_builders:
        return False, "untrusted builder"
    if provenance.source_revision != expected_revision:
        return False, "source revision mismatch"
    if provenance.subject_sha256 != _sha256(subject):
        return False, "subject digest mismatch"
    if provenance.sbom_sha256 != _sha256(canonical_json(sbom)):
        return False, "sbom digest mismatch"
    return True, "verified provenance"
