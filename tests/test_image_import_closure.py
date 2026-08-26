import re
from pathlib import Path

from app.import_closure import SHIPPED_PACKAGES, import_closure_failures


def test_reports_modules_whose_imports_cannot_be_resolved(tmp_path):
    package = tmp_path / "alpha"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "fine.py").write_text("VALUE = 1\n", encoding="utf-8")
    (package / "broken.py").write_text("import missing_dependency_xyz\n", encoding="utf-8")

    failures = import_closure_failures(("alpha",), root=tmp_path)

    assert failures == ["alpha.broken: No module named 'missing_dependency_xyz'"]


def test_every_shipped_package_imports_cleanly_from_the_repository():
    assert import_closure_failures(SHIPPED_PACKAGES, root=Path(__file__).resolve().parents[1]) == []


def test_shipped_package_list_matches_the_dockerfile_copy_list():
    dockerfile = (Path(__file__).resolve().parents[1] / "Dockerfile").read_text(encoding="utf-8")
    copied = re.findall(r"^COPY --chown=eip:eip (\S+) /app/\1$", dockerfile, flags=re.MULTILINE)
    assert tuple(copied) == SHIPPED_PACKAGES


def _first_party_packages(root: Path) -> set[str]:
    return {p.name for p in root.iterdir() if p.is_dir() and (p / "__init__.py").exists() or (p.is_dir() and any(p.glob("*.py")))}


def test_shipped_modules_that_import_unshipped_packages_are_excluded_from_the_image():
    root = Path(__file__).resolve().parents[1]
    unshipped = _first_party_packages(root) - set(SHIPPED_PACKAGES) - {"tests", "scripts"}
    dockerignore = (root / ".dockerignore").read_text(encoding="utf-8").splitlines() if (root / ".dockerignore").exists() else []
    offenders = []
    for package in SHIPPED_PACKAGES:
        for module in sorted((root / package).rglob("*.py")):
            source = module.read_text(encoding="utf-8")
            imported_roots = set(re.findall(r"^(?:from|import)\s+([A-Za-z_][A-Za-z0-9_]*)", source, flags=re.MULTILINE))
            if imported_roots & unshipped:
                relative = module.relative_to(root).as_posix()
                if relative not in dockerignore:
                    offenders.append(f"{relative} imports {sorted(imported_roots & unshipped)}")
    assert offenders == []
