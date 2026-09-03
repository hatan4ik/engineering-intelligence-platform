"""Fail CI when a repository Markdown link is missing or has the wrong path case.

The repository is developed on both case-sensitive and case-insensitive file
systems. Checking the tracked Git path, rather than only ``Path.exists()``,
prevents links that work on a Mac from failing in Linux CI or documentation
rendering.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path, PurePosixPath


LINK = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
DOCUMENTATION_REGISTER = "docs/DOCUMENT-STATUS.md"
DOCUMENTATION_PREFIXES = (
    "docs/",
    "architecture/",
    "roadmap/",
    "governance/",
    "finops/",
    "helm/temporal/",
)


def repository_paths(root: Path) -> set[str]:
    tracked = subprocess.check_output(
        ["git", "-C", str(root), "ls-files"], text=True, stderr=subprocess.DEVNULL
    )
    untracked = subprocess.check_output(
        ["git", "-C", str(root), "ls-files", "--others", "--exclude-standard"],
        text=True,
        stderr=subprocess.DEVNULL,
    )
    return {
        line
        for output in (tracked, untracked)
        for line in output.splitlines()
        if line
    }


def destination(raw_link: str) -> str | None:
    """Return the local path component of a Markdown destination, if any."""
    value = raw_link.strip()
    if not value or value.startswith(("#", "http://", "https://", "mailto:")):
        return None
    value = value.split(maxsplit=1)[0].strip("<>")
    return value.split("#", maxsplit=1)[0] or None


def repository_relative(source: str, target: str) -> str | None:
    if target.startswith("/"):
        return None
    joined = PurePosixPath(source).parent.joinpath(target)
    parts: list[str] = []
    for part in joined.parts:
        if part in ("", "."):
            continue
        if part == "..":
            if not parts:
                return None
            parts.pop()
        else:
            parts.append(part)
    return "/".join(parts)


def maintained_documentation_paths(paths: set[str]) -> set[str]:
    """Return Markdown documents that must appear in the documentation register."""
    return {
        path
        for path in paths
        if path.endswith(".md")
        and (path == "README.md" or path.startswith(DOCUMENTATION_PREFIXES))
    }


def find_document_register_failures(root: Path, paths: set[str]) -> list[str]:
    """Ensure every maintained document is discoverable from the authoritative register."""
    if DOCUMENTATION_REGISTER not in paths:
        return [f"Missing documentation register: {DOCUMENTATION_REGISTER}"]

    register = (root / DOCUMENTATION_REGISTER).read_text(encoding="utf-8")
    registered_paths: set[str] = set()
    for raw_link in LINK.findall(register):
        target = destination(raw_link)
        if target is None:
            continue
        relative = repository_relative(DOCUMENTATION_REGISTER, target)
        if relative is not None and relative.endswith(".md"):
            registered_paths.add(relative)

    expected_paths = maintained_documentation_paths(paths)
    expected_paths.discard(DOCUMENTATION_REGISTER)
    missing_paths = sorted(expected_paths - registered_paths)
    return [
        f"Documentation register omits maintained document: {path}"
        for path in missing_paths
    ]


def find_failures(root: Path) -> list[str]:
    paths = repository_paths(root)
    canonical_case = {path.casefold(): path for path in paths}
    directories = {
        str(PurePosixPath(path).parent)
        for path in paths
        if str(PurePosixPath(path).parent) != "."
    }
    canonical_directories = {path.casefold(): path for path in directories}
    failures: list[str] = []
    for source in sorted(path for path in paths if path.endswith(".md")):
        content = (root / source).read_text(encoding="utf-8")
        for raw_link in LINK.findall(content):
            target = destination(raw_link)
            if target is None:
                continue
            relative = repository_relative(source, target)
            if relative is None:
                failures.append(f"Unsupported local link in {source}: {raw_link}")
            elif relative in paths or relative in directories:
                continue
            elif actual := canonical_case.get(relative.casefold()):
                failures.append(
                    f"Case-mismatched link in {source}: {raw_link} (tracked path: {actual})"
                )
            elif actual := canonical_directories.get(relative.casefold()):
                failures.append(
                    f"Case-mismatched link in {source}: {raw_link} (tracked directory: {actual})"
                )
            else:
                failures.append(f"Broken link in {source}: {raw_link}")
    failures.extend(find_document_register_failures(root, paths))
    return failures


def main() -> int:
    failures = find_failures(Path.cwd())
    print("\n".join(failures))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
