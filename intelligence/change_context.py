from __future__ import annotations

from dataclasses import dataclass

from .extractors import service_from_path
from .risk import ChangeContext


@dataclass(frozen=True)
class HistoricalFailure:
    service: str
    fingerprint: str
    failed: bool = True


def build_change_context(
    *,
    paths: list[str],
    known_services: set[str],
    tests_present: bool,
    historical_failures: list[HistoricalFailure] | None = None,
) -> ChangeContext:
    services = sorted({s for p in paths if (s := service_from_path(p, known_services))})
    lowered = [p.lower() for p in paths]
    touches_iac = any(
        p.endswith((".tf", ".bicep")) or "/terraform/" in f"/{p}" or "/helm/" in f"/{p}"
        for p in lowered
    )
    touches_security = any(
        any(token in p for token in ("iam", "rbac", "policy", "identity", "auth", "keyvault", "secret"))
        for p in lowered
    )
    failures = historical_failures or []
    similar_failed = sum(1 for f in failures if f.failed and f.service in services)
    return ChangeContext(
        changed_services=tuple(services),
        files_changed=len(paths),
        touches_iac=touches_iac,
        touches_identity_or_security=touches_security,
        weak_test_evidence=not tests_present,
        similar_failed_changes=similar_failed,
    )
