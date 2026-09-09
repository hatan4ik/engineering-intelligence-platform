from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Protocol


@dataclass(frozen=True)
class LockLease:
    lease_id: str
    service_id: str
    locked_services: tuple[str, ...]
    acquired_at: datetime
    expires_at: datetime

    def is_expired(self, now: datetime | None = None) -> bool:
        current = now if now is not None else datetime.now(timezone.utc)
        return current >= self.expires_at


@dataclass(frozen=True)
class LockoutRefusal:
    conflicting_service: str
    active_lease_id: str
    reason: str


class BlastRadiusLockManager(Protocol):
    def acquire(
        self,
        service_id: str,
        impacted_services: tuple[str, ...],
        *,
        ttl_seconds: float = 300.0,
        now: datetime | None = None,
    ) -> tuple[LockLease | None, LockoutRefusal | None]: ...

    def release(self, lease: LockLease) -> bool: ...

    def active_leases(self, *, now: datetime | None = None) -> tuple[LockLease, ...]: ...


class InMemoryConcurrencyLockManager:
    """In-memory concurrency lockout manager tracking in-flight remediation boundaries."""

    def __init__(self) -> None:
        self._leases: dict[str, LockLease] = {}

    def _prune_expired(self, moment: datetime) -> None:
        expired = [lid for lid, lease in self._leases.items() if lease.is_expired(moment)]
        for lid in expired:
            del self._leases[lid]

    def acquire(
        self,
        service_id: str,
        impacted_services: tuple[str, ...],
        *,
        ttl_seconds: float = 300.0,
        now: datetime | None = None,
    ) -> tuple[LockLease | None, LockoutRefusal | None]:
        moment = now if now is not None else datetime.now(timezone.utc)
        self._prune_expired(moment)

        target_scope = {service_id, *impacted_services}

        for active_lease in self._leases.values():
            active_scope = {active_lease.service_id, *active_lease.locked_services}
            overlap = target_scope.intersection(active_scope)
            if overlap:
                conflicting = sorted(overlap)[0]
                reason = (
                    f"concurrency-lockout: service '{conflicting}' is under active remediation "
                    f"by lease '{active_lease.lease_id}'"
                )
                return None, LockoutRefusal(
                    conflicting_service=conflicting,
                    active_lease_id=active_lease.lease_id,
                    reason=reason,
                )

        lease_id = f"lease-{uuid.uuid4().hex[:12]}"
        expires_at = moment + timedelta(seconds=ttl_seconds)
        lease = LockLease(
            lease_id=lease_id,
            service_id=service_id,
            locked_services=tuple(sorted(target_scope)),
            acquired_at=moment,
            expires_at=expires_at,
        )
        self._leases[lease_id] = lease
        return lease, None

    def release(self, lease: LockLease) -> bool:
        if lease.lease_id in self._leases:
            del self._leases[lease.lease_id]
            return True
        return False

    def active_leases(self, *, now: datetime | None = None) -> tuple[LockLease, ...]:
        moment = now if now is not None else datetime.now(timezone.utc)
        self._prune_expired(moment)
        return tuple(self._leases.values())

