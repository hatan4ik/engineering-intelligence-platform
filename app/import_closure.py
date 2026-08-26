"""Verify that every module shipped in the release image can be imported.

The Dockerfile copies an explicit list of first-party packages. A package that
imports a sibling the image does not carry (for example ``control_plane.workflows``
importing ``intelligence``) is a latent ``ModuleNotFoundError`` that only surfaces
when a request first touches it. This module walks the shipped packages and
imports every module so the failure happens in CI, not in production.

Run inside the built image::

    python -m app.import_closure
"""
from __future__ import annotations

import importlib
import pkgutil
import sys
from pathlib import Path
from typing import Iterable

# Keep in sync with the ``COPY --chown=eip:eip <package> /app/<package>`` lines in
# the Dockerfile; ``tests/test_image_import_closure.py`` asserts they match.
SHIPPED_PACKAGES: tuple[str, ...] = (
    "app",
    "company_brain",
    "feedback",
    "finops",
    "integrations",
    "ingestion",
    "intelligence",
    "portal",
    "product",
    "security",
    "telemetry",
    "control_plane",
    "orchestration",
    "state",
)


def import_closure_failures(packages: Iterable[str], *, root: Path) -> list[str]:
    """Import every module under ``packages`` (relative to ``root``); return failures."""

    root = Path(root).resolve()
    root_text = str(root)
    inserted = root_text not in sys.path
    if inserted:
        sys.path.insert(0, root_text)
    failures: list[str] = []
    try:
        for package in packages:
            package_dir = root / package
            if not package_dir.is_dir():
                failures.append(f"{package}: package directory not found under {root}")
                continue
            for name in _module_names(package, package_dir):
                try:
                    importlib.import_module(name)
                except Exception as exc:  # noqa: BLE001 - any import-time error is a shipping defect
                    failures.append(f"{name}: {exc}")
    finally:
        if inserted:
            sys.path.remove(root_text)
    return failures


def _module_names(package: str, package_dir: Path) -> list[str]:
    names = [package]
    for info in pkgutil.walk_packages([str(package_dir)], prefix=f"{package}."):
        names.append(info.name)
    return names


def main(argv: list[str] | None = None) -> int:
    packages = tuple(argv) if argv else SHIPPED_PACKAGES
    failures = import_closure_failures(packages, root=Path.cwd())
    for failure in failures:
        print(f"import closure failure: {failure}")
    if failures:
        return 1
    print(f"import closure verified for {len(packages)} packages")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
