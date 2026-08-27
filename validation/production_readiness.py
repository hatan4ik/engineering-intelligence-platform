from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from collections.abc import Mapping as AbcMapping
from pathlib import Path
from typing import Mapping

from resilience.certification import CertificationReport
from validation.soak import SoakReport


class ReadinessArea(StrEnum):
    INTEGRATIONS = "integrations"
    IDENTITY = "identity"
    RELIABILITY = "reliability"
    SECURITY = "security"
    OBSERVABILITY = "observability"
    DATA = "data"
    L3 = "l3-certification"


@dataclass(frozen=True)
class ReadinessEvidence:
    key: str
    area: ReadinessArea
    passed: bool
    evidence_ref: str
    note: str = ""


@dataclass(frozen=True)
class ProductionReadinessReport:
    ready: bool
    score: float
    passed: tuple[str, ...]
    missing: tuple[str, ...]
    evidence_refs: tuple[str, ...]


REQUIRED_KEYS = frozenset({
    "real-source-integration",
    "entra-production-auth",
    "private-network-path",
    "ha-state-backend",
    "backup-restore-drill",
    "audit-export",
    "security-adversarial-suite",
    "control-plane-slo",
    "production-like-soak",
    "rollback-drill",
    "kill-switch-drill",
    "independent-verification",
})


def evaluate_production_readiness(
    evidence: tuple[ReadinessEvidence, ...],
    *,
    l3_report: CertificationReport | None = None,
    soak_hours: float = 0.0,
    soak_report: SoakReport | None = None,
    minimum_soak_hours: float = 168.0,
    observed_metrics: Mapping[str, float] | None = None,
) -> ProductionReadinessReport:
    """Fail-closed gate separating working reference code from earned production proof.

    `soak_hours` remains for backwards-compatible/local evaluation. Production proof
    should pass a `SoakReport`, which binds elapsed time to continuous timestamped
    passing evidence and contributes its artifact references to the report.
    """
    by_key = {item.key: item for item in evidence}
    missing: list[str] = []
    passed: list[str] = []
    refs: list[str] = []

    for key in sorted(REQUIRED_KEYS):
        item = by_key.get(key)
        if item is None or not item.passed or not item.evidence_ref.strip():
            missing.append(key)
            continue
        passed.append(key)
        refs.append(item.evidence_ref)

    effective_soak_hours = soak_report.continuous_hours if soak_report is not None else soak_hours
    if soak_report is not None:
        refs.extend(soak_report.evidence_refs)
        if not soak_report.qualifies:
            missing.append("auditable-soak-not-qualified")
    if effective_soak_hours < minimum_soak_hours:
        missing.append(f"soak-hours<{minimum_soak_hours:g}")
    else:
        passed.append("soak-duration")

    if l3_report is None or not l3_report.l3_eligible:
        missing.append("l3-certification-evidence")
    else:
        passed.append("l3-certification-evidence")
        refs.append(l3_report.evidence_digest)

    metrics = dict(observed_metrics or {})
    if metrics.get("control_plane_success_rate", 0.0) < 0.99:
        missing.append("control-plane-success-rate>=0.99")
    else:
        passed.append("control-plane-success-rate")
    if metrics.get("audit_write_success_rate", 0.0) < 1.0:
        missing.append("audit-write-success-rate=1.0")
    else:
        passed.append("audit-write-success-rate")

    total = len(passed) + len(missing)
    score = 0.0 if total == 0 else round(len(passed) / total, 4)
    return ProductionReadinessReport(
        ready=not missing,
        score=score,
        passed=tuple(sorted(set(passed))),
        missing=tuple(sorted(set(missing))),
        evidence_refs=tuple(sorted(set(refs))),
    )


# Each required key belongs to exactly one readiness area. Deriving the area
# from the key means an evidence record only has to name the claim it proves.
READINESS_AREAS: Mapping[str, ReadinessArea] = {
    "real-source-integration": ReadinessArea.INTEGRATIONS,
    "entra-production-auth": ReadinessArea.IDENTITY,
    "private-network-path": ReadinessArea.SECURITY,
    "ha-state-backend": ReadinessArea.DATA,
    "backup-restore-drill": ReadinessArea.DATA,
    "audit-export": ReadinessArea.SECURITY,
    "security-adversarial-suite": ReadinessArea.SECURITY,
    "control-plane-slo": ReadinessArea.OBSERVABILITY,
    "production-like-soak": ReadinessArea.RELIABILITY,
    "rollback-drill": ReadinessArea.RELIABILITY,
    "kill-switch-drill": ReadinessArea.RELIABILITY,
    "independent-verification": ReadinessArea.L3,
}

@dataclass(frozen=True)
class ReadinessEvidenceLoad:
    """What a registry directory yielded, including what it could not use."""

    evidence: tuple[ReadinessEvidence, ...]
    files_read: int
    ignored: tuple[str, ...]


def _record_key(record: Mapping[str, object]) -> str | None:
    """The readiness item a record proves: its structured ``readiness_key`` only.

    The free-text ``claim`` is never parsed. A record that does not name a key
    is not readiness evidence, however its prose reads.
    """
    value = record.get("readiness_key")
    if isinstance(value, str) and value in REQUIRED_KEYS:
        return value
    return None


def _record_passed(record: Mapping[str, object]) -> bool:
    """Whether the record's ``result`` records a pass.

    Mirrors ``EvidenceRecord.passed``: the verdict is the first ``;``-separated
    segment of ``result``, compared exactly to ``pass``. There is no ``passed``
    boolean in the schema, so none is read.
    """
    result = record.get("result")
    if not isinstance(result, str):
        return False
    return result.split(";", 1)[0].strip().lower() == "pass"


def _record_reference(record: Mapping[str, object]) -> str:
    """The first retained artifact this record points at.

    ``evidence_id`` is deliberately not a fallback: it identifies the record,
    not anything a reviewer can go and read. A record that lists no artifact has
    nothing retained behind it.
    """
    artifacts = record.get("artifacts")
    if isinstance(artifacts, (list, tuple)):
        for item in artifacts:
            if isinstance(item, str) and item.strip():
                return item.strip()
    return ""


def readiness_evidence_from_record(record: Mapping[str, object]) -> ReadinessEvidence | None:
    """Map one evidence record onto a readiness key, or None if it names none.

    The registry record schema is defined by ``docs/PRODUCTION-EVIDENCE.md`` and
    ``validation.evidence_records``. This reader keys on the structured fields
    only -- ``readiness_key``, ``result``, ``artifacts`` -- and is strict about
    what counts as passing: a record with no retained artifact reference is not
    evidence, whatever its result says.
    """
    key = _record_key(record)
    if key is None:
        return None
    note_parts = [str(record[field]) for field in ("method", "basis") if record.get(field)]
    return ReadinessEvidence(
        key=key,
        area=READINESS_AREAS[key],
        passed=_record_passed(record),
        evidence_ref=_record_reference(record),
        note="; ".join(note_parts),
    )


def load_readiness_evidence(directory: str | Path) -> ReadinessEvidenceLoad:
    """Read every ``*.json`` file in an evidence registry directory.

    A missing directory is not an error: it means no evidence exists, which is
    the same as nothing being proven.
    """
    root = Path(directory)
    evidence: list[ReadinessEvidence] = []
    ignored: list[str] = []
    files = sorted(root.glob("*.json")) if root.is_dir() else []
    for path in files:
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            ignored.append(f"{path.name}: unreadable ({exc})")
            continue
        records = loaded if isinstance(loaded, list) else [loaded]
        for index, record in enumerate(records):
            if not isinstance(record, AbcMapping):
                ignored.append(f"{path.name}[{index}]: not a JSON object")
                continue
            item = readiness_evidence_from_record(record)
            if item is None:
                ignored.append(f"{path.name}[{index}]: carries no readiness_key naming a required item")
                continue
            evidence.append(item)
    return ReadinessEvidenceLoad(
        evidence=tuple(evidence), files_read=len(files), ignored=tuple(ignored)
    )
