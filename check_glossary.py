"""Keep documentation hover terms aligned with the canonical Company Brain glossary."""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path

from check_links import maintained_documentation_paths, repository_paths


GLOSSARY_PATH = "docs/GLOSSARY.md"
TABLE_TERM = re.compile(r"^[A-Za-z][A-Za-z0-9/]*$")
HOVER_TERM = re.compile(r'<span\s+title="(?P<title>[^"]+)">(?P<term>[^<]+)</span>')
INLINE_CODE = re.compile(r"`[^`]*`")


def glossary_entries(content: str) -> dict[str, str]:
    """Return term-to-expansion definitions from the glossary's three-column tables."""
    entries: dict[str, str] = {}
    for line in content.splitlines():
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) != 3:
            continue
        term, expansion, _ = cells
        if term in {"Term", "Level"} or not TABLE_TERM.fullmatch(term):
            continue
        entries[term] = expansion
    return entries


def prose_only(content: str) -> str:
    """Remove fenced code blocks, where literal hover-markup examples are allowed."""
    lines: list[str] = []
    fenced = False
    for line in content.splitlines():
        if line.lstrip().startswith(("```", "~~~")):
            fenced = not fenced
            continue
        if not fenced:
            lines.append(line)
    return INLINE_CODE.sub("", "\n".join(lines)).strip()


def find_hover_term_failures(
    source: str, content: str, definitions: Mapping[str, str]
) -> list[str]:
    """Report prose hover terms missing from or diverging from the glossary."""
    failures: list[str] = []
    for match in HOVER_TERM.finditer(prose_only(content)):
        term = match.group("term")
        title = match.group("title")
        expansion = definitions.get(term)
        if expansion is None:
            failures.append(f"Unknown glossary hover term in {source}: {term}")
        elif title != expansion:
            failures.append(
                f"Glossary hover title mismatch in {source}: {term} "
                f"uses {title!r}; expected {expansion!r}"
            )
    return failures


def find_failures(root: Path) -> list[str]:
    """Validate all registered documentation hover terms against the glossary."""
    glossary_file = root / GLOSSARY_PATH
    if not glossary_file.is_file():
        return [f"Missing Company Brain glossary: {GLOSSARY_PATH}"]

    definitions = glossary_entries(glossary_file.read_text(encoding="utf-8"))
    if not definitions:
        return [f"Company Brain glossary has no term definitions: {GLOSSARY_PATH}"]

    paths = maintained_documentation_paths(repository_paths(root))
    failures: list[str] = []
    for source in sorted(path for path in paths if path.endswith(".md")):
        content = (root / source).read_text(encoding="utf-8")
        failures.extend(find_hover_term_failures(source, content, definitions))
    return failures


def main() -> int:
    failures = find_failures(Path.cwd())
    print("\n".join(failures))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
