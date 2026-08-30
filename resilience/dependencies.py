"""Small synchronous bulkhead and circuit-breaker primitives for adapters.

The product uses normal synchronous SDK and HTTP adapters at its edges.  This
module deliberately does not retry calls: only an owner who can prove an
operation is idempotent may retry it.  It instead bounds concurrency and fails
fast after repeated transient dependency failures.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from threading import BoundedSemaphore, Lock
from typing import TypeVar


Result = TypeVar("Result")


class DependencyState(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half-open"


class DependencyUnavailable(RuntimeError):
    """The adapter was refused before it could consume more dependency capacity."""

    def __init__(self, dependency: str, reason: str) -> None:
        self.dependency = dependency
        self.reason = reason
        super().__init__(f"{dependency} is unavailable: {reason}")


@dataclass(frozen=True)
class DependencyLimits:
    """A bounded, reviewable resilience policy for one adapter instance."""

    max_in_flight: int = 8
    failure_threshold: int = 3
    recovery_seconds: float = 30.0

    def __post_init__(self) -> None:
        if self.max_in_flight < 1:
            raise ValueError("max_in_flight must be at least one")
        if self.failure_threshold < 1:
            raise ValueError("failure_threshold must be at least one")
        if self.recovery_seconds <= 0:
            raise ValueError("recovery_seconds must be positive")


@dataclass(frozen=True)
class DependencyHealth:
    """A safe snapshot suitable for a health endpoint or operational log."""

    dependency: str
    state: DependencyState
    consecutive_transient_failures: int
    retry_after_seconds: float


@dataclass(frozen=True)
class _Admission:
    """The breaker generation admitted to one in-flight operation."""

    generation: int
    half_open_probe: bool


class DependencyBoundary:
    """Bound one dependency's concurrency and transient-failure blast radius.

    Instances are intentionally owned by a composed adapter rather than shared
    globally: an unhealthy GitHub client must not consume OPA or Azure Monitor
    capacity. A single half-open probe decides recovery after the cool-down.
    """

    def __init__(
        self,
        dependency: str,
        limits: DependencyLimits = DependencyLimits(),
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if not dependency.strip():
            raise ValueError("dependency must be non-blank")
        self.dependency = dependency
        self.limits = limits
        self._clock = clock
        self._capacity = BoundedSemaphore(limits.max_in_flight)
        self._lock = Lock()
        self._consecutive_transient_failures = 0
        self._open_until: float | None = None
        self._half_open_probe_active = False
        # An operation admitted while closed may complete after another
        # concurrent operation has opened the circuit. Its late success must
        # not silently undo that protection.
        self._generation = 0

    def health(self) -> DependencyHealth:
        """Return the breaker state without exposing request or payload data."""

        with self._lock:
            now = self._clock()
            if self._open_until is None:
                state = DependencyState.CLOSED
                retry_after = 0.0
            elif self._open_until > now:
                state = DependencyState.OPEN
                retry_after = self._open_until - now
            else:
                state = DependencyState.HALF_OPEN
                retry_after = 0.0
            return DependencyHealth(
                dependency=self.dependency,
                state=state,
                consecutive_transient_failures=self._consecutive_transient_failures,
                retry_after_seconds=retry_after,
            )

    def call(
        self,
        operation: Callable[[], Result],
        *,
        is_transient: Callable[[Exception], bool],
    ) -> Result:
        """Run one call or refuse it when the dependency is saturated/unhealthy."""

        if not self._capacity.acquire(blocking=False):
            raise DependencyUnavailable(self.dependency, "in-flight capacity is exhausted")
        try:
            admission = self._admit()
            try:
                result = operation()
            except Exception as error:
                if is_transient(error):
                    self._record_transient_failure(admission)
                elif admission.half_open_probe:
                    # A response-level (for example 4xx) failure proves that
                    # the transport recovered; it must not leave the breaker open.
                    self._record_success(admission)
                raise
            self._record_success(admission)
            return result
        finally:
            self._capacity.release()

    def _admit(self) -> _Admission:
        with self._lock:
            now = self._clock()
            if self._open_until is not None and self._open_until > now:
                raise DependencyUnavailable(self.dependency, "circuit is open")
            if self._open_until is not None:
                if self._half_open_probe_active:
                    raise DependencyUnavailable(self.dependency, "recovery probe is already in flight")
                self._half_open_probe_active = True
                return _Admission(self._generation, half_open_probe=True)
            return _Admission(self._generation, half_open_probe=False)

    def _record_success(self, admission: _Admission) -> None:
        with self._lock:
            if admission.generation != self._generation:
                return
            if self._open_until is not None and not admission.half_open_probe:
                return
            self._consecutive_transient_failures = 0
            self._open_until = None
            self._half_open_probe_active = False

    def _record_transient_failure(self, admission: _Admission) -> None:
        with self._lock:
            if admission.generation != self._generation:
                return
            self._consecutive_transient_failures += 1
            if (
                admission.half_open_probe
                or self._consecutive_transient_failures >= self.limits.failure_threshold
            ):
                self._open_until = self._clock() + self.limits.recovery_seconds
                self._generation += 1
            self._half_open_probe_active = False
