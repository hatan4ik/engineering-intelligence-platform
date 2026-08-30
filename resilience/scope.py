"""What an L4 certification is *about*, and what invalidates it.

``architecture/l4-certification.md`` scopes certification to
``service + environment + runbook + blast-radius budget`` and says that "any
material runbook, dependency, policy, verification signal or blast-radius change
invalidates the prior assurance and requires recertification".

This module turns both sentences into two hashes:

``scope_hash()``
    identity of the certified scope. A request whose scope hash differs from a
    certification record's is simply a different scope and is not certified.

``material_inputs_hash(...)``
    identity of the inputs the assurance was derived from. When any of them
    changes the hash changes, the record stops matching, and the execution path
    refuses until the scope is recertified.

Neither function decides anything. They only make "the same thing" and "a
different thing" mechanically decidable, so no reviewer has to eyeball it.

The module deliberately has no dependencies outside the standard library: it is
imported by both the policy/execution path and the offline certification script,
and both must compute byte-identical hashes.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime, timezone
from typing import Iterable, Mapping, TypeAlias


JsonScalar: TypeAlias = str | int | float | bool | None
"""A scalar value that can appear in the canonical certification payload."""

JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]
"""The deliberately small JSON-shaped boundary used by certification hashes."""


def parse_instant(value: str) -> datetime | None:
    """Parse an ISO-8601 instant, or ``None`` if it is unreadable.

    A naive timestamp is read as UTC. ``None`` is a refusal, never "now": every
    caller treats an unreadable expiry as a reason to fail closed.
    """

    try:
        parsed = datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _canonical(payload: JsonValue) -> str:
    """Canonical JSON: sorted keys, no insignificant whitespace, stable coercion."""

    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _plain(value: object) -> JsonValue:
    """Reduce dataclasses/mappings to plain JSON-comparable structures.

    A runbook definition reaches this module either as the ``Runbook`` dataclass
    (from the execution path) or as a mapping decoded from a JSON report (from
    the certification script). Both must hash identically or the gate would
    refuse every legitimately certified scope.
    """

    if is_dataclass(value) and not isinstance(value, type):
        return _plain(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    # ``json.dumps(..., default=str)`` was the prior compatibility behaviour
    # for an unexpected runbook field. Preserve its stable representation while
    # keeping the hash input JSON-shaped instead of leaking ``Any`` inward.
    return str(value)


@dataclass(frozen=True)
class CertificationScope:
    """The four things an L4 certification is scoped to."""

    service: str
    environment: str
    runbook_id: str
    blast_radius_budget: int

    def __post_init__(self) -> None:
        for field in ("service", "environment", "runbook_id"):
            if not str(getattr(self, field)).strip():
                raise ValueError(f"certification scope {field} must not be blank")
        # A zero or negative budget authorises nothing, so it is never a scope
        # that can be certified; refusing it here keeps the executor from
        # comparing hashes of a meaningless scope.
        if int(self.blast_radius_budget) <= 0:
            raise ValueError(
                "certification scope blast_radius_budget must be a positive bounded budget"
            )

    def canonical(self) -> dict[str, JsonValue]:
        return {
            "service": str(self.service),
            "environment": str(self.environment),
            "runbook_id": str(self.runbook_id),
            "blast_radius_budget": int(self.blast_radius_budget),
        }

    def scope_hash(self) -> str:
        """Stable lowercase sha256 hex of the canonical scope."""

        return _sha256(_canonical(self.canonical()))

    def evidence_scope(self) -> str:
        """The ``scope`` string an evidence record must carry for this scope."""

        return f"{self.service}/{self.environment}/{self.runbook_id}"

    def material_inputs_hash(
        self,
        *,
        runbook_definition: object,
        policy_bundle_version: str,
        verification_signal: str,
        dependencies: Iterable[str],
    ) -> str:
        """Stable sha256 over the scope and every material input.

        Dependencies are sorted: the set of dependencies is material, the order
        in which a caller happened to list them is not.
        """

        payload: dict[str, JsonValue] = {
            "scope": self.canonical(),
            "runbook_definition": _plain(runbook_definition),
            "policy_bundle_version": str(policy_bundle_version),
            "verification_signal": str(verification_signal),
            "dependencies": [_plain(item) for item in sorted(str(item) for item in dependencies)],
        }
        return _sha256(_canonical(payload))
