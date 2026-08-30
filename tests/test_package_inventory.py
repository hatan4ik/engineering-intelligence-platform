"""The source distribution, release image, and import check are one contract."""
from __future__ import annotations

import re
import tomllib
from fnmatch import fnmatchcase
from pathlib import Path
from zipfile import ZipFile

from app.import_closure import SHIPPED_PACKAGES
from scripts.verify_package_inventory import (
    dependency_inventory_error,
    inventory_error,
    runtime_dependency_names,
    wheel_dependency_names,
    wheel_packages,
)


ROOT = Path(__file__).resolve().parents[1]


def test_setuptools_patterns_cover_exactly_the_release_inventory():
    metadata = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    finder = metadata["tool"]["setuptools"]["packages"]["find"]
    assert finder["namespaces"] is True
    patterns = finder["include"]
    declared_release_packages = {
        package
        for package in SHIPPED_PACKAGES
        if any(fnmatchcase(package, pattern) for pattern in patterns)
    }
    assert declared_release_packages == set(SHIPPED_PACKAGES)

    source_packages = {
        entry.name
        for entry in ROOT.iterdir()
        if entry.is_dir() and any(entry.rglob("*.py"))
    }
    distribution_packages = {
        package
        for package in source_packages
        if any(fnmatchcase(package, pattern) for pattern in patterns)
    }
    assert distribution_packages == set(SHIPPED_PACKAGES)


def test_ci_builds_a_wheel_and_runs_the_inventory_verifier():
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    assert "pip install -r requirements/test.txt" in workflow
    assert "pip install -r requirements/build.txt" in workflow
    assert "python -m pip wheel --no-deps --no-build-isolation" in workflow
    assert "python scripts/verify_package_inventory.py /tmp/eip-wheel/*.whl" in workflow


def test_non_isolated_wheel_check_installs_the_exact_declared_build_backend():
    metadata = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    build_requirements = (ROOT / "requirements" / "build.txt").read_text(encoding="utf-8").splitlines()

    assert metadata["build-system"]["requires"] == ["setuptools==75.8.0"]
    assert build_requirements == [
        "# Build-only dependency for the intentionally non-isolated wheel inventory check.",
        "# Keep this pin synchronized with pyproject.toml's [build-system].requires.",
        "setuptools==75.8.0",
    ]


def test_runtime_manifest_and_project_metadata_describe_the_same_dependencies():
    metadata = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    project_dependencies = {
        re.match(r"[A-Za-z0-9][A-Za-z0-9_.-]*", dependency).group(0).replace("_", "-").lower()
        for dependency in metadata["project"]["dependencies"]
    }
    assert project_dependencies == runtime_dependency_names()
    assert "azure-servicebus" in project_dependencies
    assert "pytest" not in project_dependencies

    test_dependencies = metadata["project"]["optional-dependencies"]["test"]
    assert test_dependencies == ["pytest==9.0.3"]
    assert (ROOT / "requirements" / "test.txt").read_text(encoding="utf-8").splitlines() == [
        "# Test-only dependencies. Keep these out of the release image's runtime closure.",
        "pytest==9.0.3",
    ]


def test_wheel_inventory_reports_missing_and_unexpected_release_packages(tmp_path):
    wheel_path = tmp_path / "example.whl"
    with ZipFile(wheel_path, "w") as wheel:
        wheel.writestr("app/main.py", "")
        wheel.writestr("unexpected/module.py", "")

    assert wheel_packages(wheel_path) == {"app", "unexpected"}
    error = inventory_error(wheel_path)
    assert error is not None
    assert "missing from wheel:" in error
    assert "company_brain" in error
    assert "unexpected Python package in wheel: unexpected" in error


def test_dependency_inventory_reports_runtime_metadata_drift(tmp_path):
    wheel_path = tmp_path / "example.whl"
    with ZipFile(wheel_path, "w") as wheel:
        wheel.writestr(
            "example-0.0.0.dist-info/METADATA",
            "Metadata-Version: 2.4\nRequires-Dist: fastapi\nRequires-Dist: pytest; extra == 'test'\n",
        )

    assert wheel_dependency_names(wheel_path) == {"fastapi"}
    error = dependency_inventory_error(wheel_path)
    assert error is not None
    assert "missing runtime dependencies from wheel:" in error
    assert "azure-servicebus" in error
