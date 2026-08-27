"""The evidence registry contract from ``docs/PRODUCTION-EVIDENCE.md``.

A record is a *retained claim about a real run*, not a status label. This module
only parses, validates, and groups records. It never decides that a stage,
capability, or autonomy tier has been proven, and an absent record always means
**not proven** — never "assume yes".

Records are plain JSON on disk (``docs/evidence/<evidence_id>.json``) so any
tool can read the registry without importing this package.
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

#: The nine fields of the evidence record table in docs/PRODUCTION-EVIDENCE.md.
REQUIRED_FIELDS: tuple[str, ...] = (
    "evidence_id",
    "scope",
    "change",
    "claim",
    "method",
    "result",
    "independence",
    "artifacts",
    "approval",
)

#: How the result was obtained. ``measured`` means an actual observed run and is
#: the only basis that may support a promotion decision; ``derived`` is computed
#: from measured records; ``modeled`` is a simulation or rehearsal.
BASES: tuple[str, ...] = ("measured", "derived", "modeled")

#: The promotion decisions in the "Minimum evidence by decision" table.
DECISIONS: tuple[str, ...] = (
    "real-data-pilot",
    "pr-guardian-advisory",
    "blocking-pr-rule",
    "l3-remediation-pilot",
    "l4-promotion",
)

#: An evidence id is also a filename, so it is restricted to a safe shape.
EVIDENCE_ID = re.compile(r"^[a-z0-9][a-z0-9._-]*$")

#: Structured vocabulary that readers key on. ``readiness_key`` names the
#: production-readiness item a record proves (one of
#: ``validation.production_readiness.REQUIRED_KEYS``); ``controls`` names the
#: L4 certification controls it attests (``architecture/l4-certification.md``).
#: Readers match these fields exactly and never parse the free-text ``claim``.
_STRUCTURED_FIELDS: frozenset[str] = frozenset({"readiness_key", "controls"})

_ALL_FIELDS: frozenset[str] = (
    frozenset(REQUIRED_FIELDS) | {"basis", "decision", "source_run_url"} | _STRUCTURED_FIELDS
)


def _readiness_keys() -> frozenset[str]:
    # Imported lazily: production_readiness owns the key vocabulary and must not
    # depend on this module.
    from validation.production_readiness import REQUIRED_KEYS

    return frozenset(REQUIRED_KEYS)


@dataclass(frozen=True)
class EvidenceRecord:
    """One immutable evidence record. Construct it through :func:`validate_record`."""

    evidence_id: str
    scope: str
    change: str
    claim: str
    method: str
    result: str
    independence: str
    artifacts: tuple[str, ...]
    approval: str
    basis: str
    decision: str
    source_run_url: str | None = None
    readiness_key: str | None = None
    controls: tuple[str, ...] = ()

    @property
    def passed(self) -> bool:
        """Whether ``result`` records a pass.

        ``result`` is free text by contract ("pass/fail, quantitative result,
        timestamps, ..."), so the verdict is its first ``;``-separated segment,
        compared exactly: ``"pass; 2/2 principals behaved"`` passes,
        ``"passed with caveats"`` and ``"fail"`` do not.
        """

        return self.result.split(";", 1)[0].strip().lower() == "pass"

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["artifacts"] = list(self.artifacts)
        if self.source_run_url is None:
            payload.pop("source_run_url")
        if self.readiness_key is None:
            payload.pop("readiness_key")
        if not self.controls:
            payload.pop("controls")
        else:
            payload["controls"] = list(self.controls)
        return payload


def _text_violations(mapping: Mapping[str, Any], field: str) -> list[str]:
    if field not in mapping:
        return [f"{field}: required field is missing"]
    value = mapping[field]
    if not isinstance(value, str):
        return [f"{field}: must be a string, got {type(value).__name__}"]
    if not value.strip():
        return [f"{field}: must not be blank"]
    return []


def validate_record(mapping: Mapping[str, Any]) -> EvidenceRecord:
    """Validate one record mapping, raising ``ValueError`` naming every violation."""

    if not isinstance(mapping, Mapping):
        raise ValueError(f"evidence record must be a JSON object, got {type(mapping).__name__}")

    violations: list[str] = []
    for field in sorted(set(mapping) - _ALL_FIELDS):
        violations.append(f"{field}: unknown field")

    for field in REQUIRED_FIELDS:
        if field == "artifacts":
            continue
        violations.extend(_text_violations(mapping, field))

    evidence_id = mapping.get("evidence_id")
    if isinstance(evidence_id, str) and evidence_id.strip() and not EVIDENCE_ID.match(evidence_id):
        violations.append(
            "evidence_id: must match "
            f"{EVIDENCE_ID.pattern} so it is a safe file name (lowercase, no spaces or path separators)"
        )

    artifacts = mapping.get("artifacts")
    if "artifacts" not in mapping:
        violations.append("artifacts: required field is missing")
    elif not isinstance(artifacts, (list, tuple)) or isinstance(artifacts, str):
        violations.append("artifacts: must be a list of signed links or digests")
    elif not artifacts:
        violations.append("artifacts: must list at least one signed link or digest")
    elif any(not isinstance(item, str) or not item.strip() for item in artifacts):
        violations.append("artifacts: every entry must be a non-blank string")

    violations.extend(_text_violations(mapping, "basis"))
    basis = mapping.get("basis")
    if isinstance(basis, str) and basis.strip() and basis not in BASES:
        violations.append(f"basis: must be one of {', '.join(BASES)}")

    violations.extend(_text_violations(mapping, "decision"))
    decision = mapping.get("decision")
    if isinstance(decision, str) and decision.strip() and decision not in DECISIONS:
        violations.append(f"decision: must be one of {', '.join(DECISIONS)}")

    source_run_url = mapping.get("source_run_url")
    if source_run_url is not None:
        if not isinstance(source_run_url, str) or not source_run_url.strip():
            violations.append("source_run_url: must be a non-blank URL when present")
        elif not source_run_url.startswith("https://"):
            violations.append("source_run_url: must be an https URL")
    if basis == "measured" and not (isinstance(source_run_url, str) and source_run_url.strip()):
        violations.append(
            "source_run_url: a measured record must cite the run it was measured from"
        )

    readiness_key = mapping.get("readiness_key")
    if readiness_key is not None:
        if not isinstance(readiness_key, str) or not readiness_key.strip():
            violations.append("readiness_key: must be a non-blank string when present")
        elif readiness_key not in _readiness_keys():
            violations.append(
                "readiness_key: must be one of " + ", ".join(sorted(_readiness_keys()))
            )

    controls: tuple[str, ...] = ()
    raw_controls = mapping.get("controls")
    if raw_controls is not None:
        if not isinstance(raw_controls, (list, tuple)) or isinstance(raw_controls, str):
            violations.append("controls: must be a list of control names")
        elif any(not isinstance(item, str) or not item.strip() for item in raw_controls):
            violations.append("controls: every entry must be a non-blank control name")
        else:
            seen: list[str] = []
            for item in raw_controls:
                name = item.strip()
                if name not in seen:
                    seen.append(name)
            controls = tuple(seen)

    if violations:
        raise ValueError("invalid evidence record: " + "; ".join(sorted(violations)))

    return EvidenceRecord(
        evidence_id=str(mapping["evidence_id"]),
        scope=str(mapping["scope"]),
        change=str(mapping["change"]),
        claim=str(mapping["claim"]),
        method=str(mapping["method"]),
        result=str(mapping["result"]),
        independence=str(mapping["independence"]),
        artifacts=tuple(str(item) for item in mapping["artifacts"]),
        approval=str(mapping["approval"]),
        basis=str(mapping["basis"]),
        decision=str(mapping["decision"]),
        source_run_url=str(source_run_url) if source_run_url is not None else None,
        readiness_key=str(readiness_key) if readiness_key is not None else None,
        controls=controls,
    )


def load_registry(directory: str | Path) -> tuple[EvidenceRecord, ...]:
    """Load every ``*.json`` record in ``directory`` (sorted). Empty means not proven."""

    path = Path(directory)
    if not path.is_dir():
        raise ValueError(f"evidence registry directory does not exist: {path}")

    records: list[EvidenceRecord] = []
    for file in sorted(path.glob("*.json")):
        try:
            payload = json.loads(file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError(f"{file.name}: cannot be read as JSON: {error}") from error
        try:
            record = validate_record(payload)
        except ValueError as error:
            raise ValueError(f"{file.name}: {error}") from error
        if record.evidence_id != file.stem:
            raise ValueError(
                f"{file.name}: file name does not match evidence_id {record.evidence_id!r}"
            )
        records.append(record)
    return tuple(records)


def registry_summary(records: Sequence[EvidenceRecord]) -> dict[str, Any]:
    """Group the registry by decision, scope, and basis, and report what is absent."""

    by_decision: dict[str, int] = {}
    by_scope: dict[str, int] = {}
    by_basis: dict[str, int] = {}
    for record in records:
        by_decision[record.decision] = by_decision.get(record.decision, 0) + 1
        by_scope[record.scope] = by_scope.get(record.scope, 0) + 1
        by_basis[record.basis] = by_basis.get(record.basis, 0) + 1
    return {
        "total": len(records),
        "by_decision": dict(sorted(by_decision.items())),
        "by_scope": dict(sorted(by_scope.items())),
        "by_basis": dict(sorted(by_basis.items())),
        # Absence only. This function never reports that a decision is proven;
        # that judgement belongs to the reviewers named in each record.
        "decisions_without_records": [name for name in DECISIONS if name not in by_decision],
    }
