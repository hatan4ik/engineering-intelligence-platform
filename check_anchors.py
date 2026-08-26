"""Fail CI when a same-document Markdown anchor cannot be resolved."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path


HEADER = re.compile(r"^#+\s+(.*?)$", flags=re.MULTILINE)
ANCHOR_LINK = re.compile(r"\[[^\]]*\]\((#[^)]+)\)")


def normalize_header(header: str) -> str:
    return "#" + re.sub(r"[^a-z0-9\-]", "", header.lower().replace(" ", "-"))


def repository_markdown(root: Path) -> list[str]:
    tracked = subprocess.check_output(
        ["git", "-C", str(root), "ls-files", "*.md"], text=True, stderr=subprocess.DEVNULL
    )
    untracked = subprocess.check_output(
        ["git", "-C", str(root), "ls-files", "--others", "--exclude-standard", "*.md"],
        text=True,
        stderr=subprocess.DEVNULL,
    )
    return sorted({line for output in (tracked, untracked) for line in output.splitlines() if line})


def find_failures(root: Path) -> list[str]:
    failures: list[str] = []
    for source in repository_markdown(root):
        content = (root / source).read_text(encoding="utf-8")
        headers = {normalize_header(header) for header in HEADER.findall(content)}
        for link in ANCHOR_LINK.findall(content):
            if link not in headers:
                failures.append(f"Broken anchor in {source}: {link}")
    return failures


def main() -> int:
    failures = find_failures(Path.cwd())
    print("\n".join(failures))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
