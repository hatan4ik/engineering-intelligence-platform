"""Durable, idempotent records for PR Guardian findings and explicit outcomes.

The store intentionally persists product contracts, not GitHub payloads.  It
cannot infer a reviewer judgment from merge/close status; callers must record
an explicit ``FindingOutcome`` or an independent correlation reference.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from .contracts import (
    EvidenceBasis,
    EvidenceBundle,
    EvidenceReference,
    FindingAction,
    FindingOutcome,
    PRFinding,
    ReviewerRiskDisposition,
    ReviewerUtilityDisposition,
)


class PRGuardianStoreError(RuntimeError):
    """Raised when a durable PR Guardian record conflicts with prior history."""


class PRGuardianFindingStore(Protocol):
    def record_finding(self, finding: PRFinding) -> bool: ...
    def finding(self, finding_id: str) -> PRFinding | None: ...
    def findings_for_pull_request(
        self, *, repository: str, pr_number: int, head_sha: str | None = None
    ) -> tuple[PRFinding, ...]: ...
    def record_outcome(self, outcome: FindingOutcome) -> bool: ...
    def outcomes_for_finding(self, finding_id: str) -> tuple[FindingOutcome, ...]: ...


class SqlitePRGuardianStore:
    """Reference SQLite implementation with append-only outcome semantics."""

    def __init__(self, path: str | Path = "pr-guardian.db") -> None:
        self.path = Path(path)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path)
        db.row_factory = sqlite3.Row
        return db

    def _init_schema(self) -> None:
        with self._connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS pr_guardian_findings (
                    finding_id TEXT PRIMARY KEY,
                    repository TEXT NOT NULL,
                    pr_number INTEGER NOT NULL,
                    head_sha TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    recorded_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_pr_guardian_findings_pr
                    ON pr_guardian_findings(repository, pr_number, head_sha, finding_id);
                CREATE TABLE IF NOT EXISTS pr_guardian_outcomes (
                    outcome_key TEXT PRIMARY KEY,
                    finding_id TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    recorded_at TEXT NOT NULL,
                    FOREIGN KEY(finding_id) REFERENCES pr_guardian_findings(finding_id)
                );
                CREATE INDEX IF NOT EXISTS idx_pr_guardian_outcomes_finding
                    ON pr_guardian_outcomes(finding_id, outcome_key);
                """
            )

    def record_finding(self, finding: PRFinding) -> bool:
        payload = _canonical(_finding_payload(finding))
        with self._connect() as db:
            row = db.execute(
                "SELECT payload FROM pr_guardian_findings WHERE finding_id = ?",
                (finding.finding_id,),
            ).fetchone()
            if row is not None:
                if row["payload"] != payload:
                    raise PRGuardianStoreError(
                        "finding_id conflicts with an existing immutable finding"
                    )
                return False
            db.execute(
                """INSERT INTO pr_guardian_findings
                   (finding_id, repository, pr_number, head_sha, payload, recorded_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    finding.finding_id,
                    finding.repository,
                    finding.pr_number,
                    finding.head_sha,
                    payload,
                    _now(),
                ),
            )
        return True

    def finding(self, finding_id: str) -> PRFinding | None:
        with self._connect() as db:
            row = db.execute(
                "SELECT payload FROM pr_guardian_findings WHERE finding_id = ?",
                (finding_id,),
            ).fetchone()
        return (
            _finding_from_payload(json.loads(row["payload"]))
            if row is not None
            else None
        )

    def findings_for_pull_request(
        self, *, repository: str, pr_number: int, head_sha: str | None = None
    ) -> tuple[PRFinding, ...]:
        query = (
            "SELECT payload FROM pr_guardian_findings WHERE repository = ? AND pr_number = ?"
            + (" AND head_sha = ?" if head_sha is not None else "")
            + " ORDER BY finding_id"
        )
        args: tuple[object, ...] = (
            repository,
            pr_number,
            *(() if head_sha is None else (head_sha,)),
        )
        with self._connect() as db:
            rows = db.execute(query, args).fetchall()
        return tuple(_finding_from_payload(json.loads(row["payload"])) for row in rows)

    def record_outcome(self, outcome: FindingOutcome) -> bool:
        if self.finding(outcome.finding_id) is None:
            raise PRGuardianStoreError("an outcome requires a retained finding")
        payload = _canonical(_outcome_payload(outcome))
        outcome_key = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        with self._connect() as db:
            cursor = db.execute(
                """INSERT OR IGNORE INTO pr_guardian_outcomes
                   (outcome_key, finding_id, payload, recorded_at) VALUES (?, ?, ?, ?)""",
                (outcome_key, outcome.finding_id, payload, _now()),
            )
        return cursor.rowcount == 1

    def outcomes_for_finding(self, finding_id: str) -> tuple[FindingOutcome, ...]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT payload FROM pr_guardian_outcomes WHERE finding_id = ? ORDER BY outcome_key",
                (finding_id,),
            ).fetchall()
        return tuple(_outcome_from_payload(json.loads(row["payload"])) for row in rows)


def _finding_payload(finding: PRFinding) -> dict[str, object]:
    return {
        "finding_id": finding.finding_id,
        "repository": finding.repository,
        "pr_number": finding.pr_number,
        "head_sha": finding.head_sha,
        "severity": finding.severity,
        "summary": finding.summary,
        "correlation_id": finding.correlation_id,
        "policy_version": finding.policy_version,
        "context_version": finding.context_version,
        "context_qualified": finding.context_qualified,
        "simulated_action": finding.simulated_action.value,
        "evidence": {
            "basis": finding.evidence.basis.value,
            "references": [asdict(item) for item in finding.evidence.references],
            "limitations": list(finding.evidence.limitations),
        },
    }


def _finding_from_payload(payload: dict[str, object]) -> PRFinding:
    evidence_payload = payload["evidence"]
    if not isinstance(evidence_payload, dict):
        raise PRGuardianStoreError("stored finding evidence is invalid")
    references = evidence_payload.get("references", [])
    if not isinstance(references, list):
        raise PRGuardianStoreError("stored finding references are invalid")
    return PRFinding(
        finding_id=str(payload["finding_id"]),
        repository=str(payload["repository"]),
        pr_number=_stored_int(payload["pr_number"], field="pr_number"),
        head_sha=str(payload["head_sha"]),
        severity=str(payload["severity"]),
        summary=str(payload["summary"]),
        correlation_id=str(payload["correlation_id"]),
        policy_version=str(payload["policy_version"]),
        context_version=str(payload["context_version"]),
        context_qualified=bool(payload["context_qualified"]),
        simulated_action=FindingAction(str(payload["simulated_action"])),
        evidence=EvidenceBundle(
            basis=EvidenceBasis(str(evidence_payload["basis"])),
            references=tuple(
                EvidenceReference(
                    evidence_id=str(item["evidence_id"]),
                    source_kind=str(item["source_kind"]),
                    locator=str(item["locator"]),
                    authorized=bool(item["authorized"]),
                )
                for item in references
                if isinstance(item, dict)
            ),
            limitations=tuple(
                str(item) for item in evidence_payload.get("limitations", [])
            ),
        ),
    )


def _outcome_payload(outcome: FindingOutcome) -> dict[str, object]:
    return {
        "finding_id": outcome.finding_id,
        "reviewer_risk": outcome.reviewer_risk.value,
        "reviewer_utility": outcome.reviewer_utility.value,
        "recorded_by": outcome.recorded_by,
        "post_merge_correlation_id": outcome.post_merge_correlation_id,
    }


def _outcome_from_payload(payload: dict[str, object]) -> FindingOutcome:
    return FindingOutcome(
        finding_id=str(payload["finding_id"]),
        reviewer_risk=ReviewerRiskDisposition(str(payload["reviewer_risk"])),
        reviewer_utility=ReviewerUtilityDisposition(str(payload["reviewer_utility"])),
        recorded_by=str(payload["recorded_by"])
        if payload.get("recorded_by") is not None
        else None,
        post_merge_correlation_id=(
            str(payload["post_merge_correlation_id"])
            if payload.get("post_merge_correlation_id") is not None
            else None
        ),
    )


def _stored_int(value: object, *, field: str) -> int:
    """Restore an integer only when the local immutable payload preserved it."""

    if type(value) is not int:
        raise PRGuardianStoreError(f"stored finding {field} is invalid")
    return value


def _canonical(value: dict[str, object]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
