"""Kill a small, explicit set of safety mutants in ``DependencyBoundary``.

This is intentionally narrower than a repository-wide mutation-coverage claim.
It protects the four control invariants that prevent an unhealthy external
dependency from consuming unbounded capacity or being reopened by a stale
success. See ``docs/TARGETED-MUTATION-CONTRACT.md`` for scope and evidence
limits.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BOUNDARY_PACKAGE = ROOT / "resilience"
BOUNDARY_TEST = ROOT / "tests" / "test_dependency_boundary.py"


class TargetedMutationError(RuntimeError):
    """The mutation contract itself is malformed or cannot be executed."""


@dataclass(frozen=True)
class MutationCase:
    """One source-level change the boundary test suite must reject."""

    identifier: str
    target: str
    needle: str
    replacement: str
    invariant: str


MUTATIONS: tuple[MutationCase, ...] = (
    MutationCase(
        identifier="opens-at-failure-threshold",
        target="resilience/dependencies.py",
        needle="self._consecutive_transient_failures >= self.limits.failure_threshold",
        replacement="self._consecutive_transient_failures > self.limits.failure_threshold",
        invariant="the circuit opens on, not after, its configured transient-failure threshold",
    ),
    MutationCase(
        identifier="rejects-open-circuit",
        target="resilience/dependencies.py",
        needle="if self._open_until is not None and self._open_until > now:",
        replacement="if self._open_until is not None and self._open_until < now:",
        invariant="an open circuit refuses calls until its recovery window expires",
    ),
    MutationCase(
        identifier="rejects-bulkhead-overflow",
        target="resilience/dependencies.py",
        needle="if not self._capacity.acquire(blocking=False):",
        replacement="if False:",
        invariant="a full bulkhead refuses rather than allowing another in-flight call",
    ),
    MutationCase(
        identifier="preserves-open-circuit-from-stale-success",
        target="resilience/dependencies.py",
        needle=(
            "if admission.generation != self._generation:\n"
            "                return\n"
            "            if self._open_until is not None and not admission.half_open_probe:\n"
            "                return"
        ),
        replacement="if False:\n                return\n            if False:\n                return",
        invariant="a stale successful call cannot erase a circuit opened by another request",
    ),
)


def mutated_source(source: str, case: MutationCase) -> str:
    """Apply exactly one pre-reviewed mutation or reject a stale test contract."""

    occurrences = source.count(case.needle)
    if occurrences != 1:
        raise TargetedMutationError(
            f"{case.identifier}: expected one target occurrence, found {occurrences}"
        )
    mutated = source.replace(case.needle, case.replacement, 1)
    try:
        compile(mutated, case.target, "exec")
    except SyntaxError as error:
        raise TargetedMutationError(f"{case.identifier}: mutation is not valid Python: {error}") from error
    return mutated


def _run_boundary_test(case: MutationCase | None) -> subprocess.CompletedProcess[str]:
    with tempfile.TemporaryDirectory(prefix="eip-targeted-mutations-") as directory:
        overlay = Path(directory)
        shutil.copytree(BOUNDARY_PACKAGE, overlay / "resilience")
        test_path = overlay / BOUNDARY_TEST.name
        shutil.copy2(BOUNDARY_TEST, test_path)
        if case is not None:
            target = overlay / case.target
            target.write_text(mutated_source(target.read_text(encoding="utf-8"), case), encoding="utf-8")
        environment = os.environ.copy()
        # The copied test must import the copied package. This prevents a pass
        # from accidentally exercising the unmodified working tree.
        environment["PYTHONPATH"] = str(overlay)
        return subprocess.run(
            [sys.executable, "-m", "pytest", "-q", str(test_path)],
            cwd=overlay,
            env=environment,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )


def _result_text(result: subprocess.CompletedProcess[str]) -> str:
    output = result.stdout.strip()
    return output[-2_000:] if output else "no test output"


def verify() -> tuple[str, ...]:
    """Return every mutation that survived or failed to execute cleanly."""

    if not BOUNDARY_PACKAGE.is_dir() or not BOUNDARY_TEST.is_file():
        raise TargetedMutationError("DependencyBoundary source package or boundary test is missing")
    baseline = _run_boundary_test(None)
    if baseline.returncode != 0:
        return (
            "unmutated DependencyBoundary test suite failed; cannot establish mutation evidence:\n"
            + _result_text(baseline),
        )

    failures: list[str] = []
    for case in MUTATIONS:
        result = _run_boundary_test(case)
        if result.returncode == 1:
            print(f"mutation {case.identifier}: killed")
            continue
        if result.returncode == 0:
            failures.append(f"mutation {case.identifier} survived: {case.invariant}")
            continue
        failures.append(
            f"mutation {case.identifier} produced pytest exit {result.returncode}, not a test failure:\n"
            + _result_text(result)
        )
    return tuple(failures)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list", action="store_true", help="print the reviewed mutation identifiers")
    args = parser.parse_args(argv)
    if args.list:
        for case in MUTATIONS:
            print(f"{case.identifier}: {case.invariant}")
        return 0
    try:
        failures = verify()
    except TargetedMutationError as error:
        print(f"targeted mutation contract error: {error}", file=sys.stderr)
        return 2
    for failure in failures:
        print(failure, file=sys.stderr)
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
