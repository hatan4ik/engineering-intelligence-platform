from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ArtifactProvenance:
    image: str
    digest: str
    sbom_present: bool
    signed: bool
    builder: str
    source_commit: str


def verify_provenance(prov: ArtifactProvenance, *, trusted_builders: tuple[str, ...]) -> tuple[bool, tuple[str, ...]]:
    failures: list[str] = []
    if not prov.digest.startswith("sha256:"):
        failures.append("image digest is not immutable sha256")
    if not prov.sbom_present:
        failures.append("SBOM missing")
    if not prov.signed:
        failures.append("artifact signature missing")
    if prov.builder not in trusted_builders:
        failures.append("untrusted builder")
    if not prov.source_commit:
        failures.append("source commit missing")
    return (not failures, tuple(failures))
