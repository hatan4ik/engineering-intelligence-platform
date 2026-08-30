"""Verify that the built distributable carries every release-image package.

``app.import_closure.SHIPPED_PACKAGES`` is the canonical release inventory.
The Dockerfile-copy assertion runs in pytest; this script closes the remaining
gap by inspecting the wheel produced from pyproject.toml in CI.
"""
from __future__ import annotations

import re
import sys
from email import message_from_bytes
from pathlib import Path
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.import_closure import SHIPPED_PACKAGES


RUNTIME_REQUIREMENTS = ROOT / "app" / "requirements.txt"
_DISTRIBUTION_METADATA_SUFFIX = ".dist-info/METADATA"
_PACKAGE_NAME = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9_.-]*)")


def _normalized_package_name(requirement: str) -> str:
    """Extract a PEP 503-normalized distribution name from a requirement."""

    match = _PACKAGE_NAME.match(requirement)
    if match is None:
        raise ValueError(f"invalid requirement metadata: {requirement!r}")
    return re.sub(r"[-_.]+", "-", match.group(1)).lower()


def wheel_packages(path: Path) -> set[str]:
    """Return top-level Python package directories present in a wheel."""

    with ZipFile(path) as wheel:
        return {
            name.split("/", 1)[0]
            for name in wheel.namelist()
            if "/" in name and name.endswith(".py")
        }


def runtime_dependency_names(path: Path = RUNTIME_REQUIREMENTS) -> set[str]:
    """Read the release-image dependency names from its pinned manifest."""

    return {
        _normalized_package_name(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }


def wheel_dependency_names(path: Path) -> set[str]:
    """Read unconditional runtime dependencies from wheel core metadata."""

    with ZipFile(path) as wheel:
        metadata_paths = [
            name for name in wheel.namelist() if name.endswith(_DISTRIBUTION_METADATA_SUFFIX)
        ]
        if len(metadata_paths) != 1:
            raise ValueError("wheel must contain exactly one .dist-info/METADATA file")
        metadata = message_from_bytes(wheel.read(metadata_paths[0]))
    dependencies: set[str] = set()
    for requirement in metadata.get_all("Requires-Dist", []):
        # Extras are not part of the release-image dependency closure. A
        # semicolon marker makes this distinction explicit in wheel metadata.
        base, separator, marker = requirement.partition(";")
        if separator and "extra" in marker:
            continue
        dependencies.add(_normalized_package_name(base))
    return dependencies


def dependency_inventory_error(path: Path) -> str | None:
    """Report drift between Docker's pinned runtime manifest and wheel metadata."""

    expected = runtime_dependency_names()
    try:
        actual = wheel_dependency_names(path)
    except (OSError, ValueError) as error:
        return f"cannot inspect wheel runtime dependencies: {error}"
    missing = sorted(expected - actual)
    unexpected = sorted(actual - expected)
    problems: list[str] = []
    if missing:
        problems.append("missing runtime dependencies from wheel: " + ", ".join(missing))
    if unexpected:
        problems.append("unexpected runtime dependencies in wheel: " + ", ".join(unexpected))
    return "; ".join(problems) or None


def inventory_error(path: Path) -> str | None:
    expected = set(SHIPPED_PACKAGES)
    actual = wheel_packages(path)
    missing = sorted(expected - actual)
    unexpected = sorted(actual - expected)
    problems: list[str] = []
    if missing:
        problems.append("missing from wheel: " + ", ".join(missing))
    if unexpected:
        problems.append("unexpected Python package in wheel: " + ", ".join(unexpected))
    dependency_error = dependency_inventory_error(path)
    if dependency_error:
        problems.append(dependency_error)
    return "; ".join(problems) or None


def main(argv: list[str] | None = None) -> int:
    paths = [Path(value) for value in (argv if argv is not None else sys.argv[1:])]
    if len(paths) != 1:
        raise SystemExit("usage: python scripts/verify_package_inventory.py <wheel>")
    error = inventory_error(paths[0])
    if error:
        print(f"package inventory mismatch: {error}", file=sys.stderr)
        return 1
    print(f"package inventory verified for {len(SHIPPED_PACKAGES)} release packages")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
