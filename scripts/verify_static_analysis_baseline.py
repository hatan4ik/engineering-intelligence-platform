"""Run the versioned static-analysis baseline and refuse regression.

The baseline is a ratchet, not an exemption: an existing diagnostic may remain
temporarily, but a pull request may not increase any recorded count. The script
does not infer quality from annotations and it does not grant production
readiness; it only makes the current type/lint debt visible and non-increasing.
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
import sys
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASELINE = ROOT / "requirements" / "static-analysis-baseline.json"
ERROR = re.compile(r"^.+: error: .+$", re.MULTILINE)


class StaticAnalysisBaselineError(ValueError):
    """The ratchet configuration or a required tool cannot be used."""


@dataclass(frozen=True)
class ToolBudget:
    name: str
    version: str
    maximum_errors: int


@dataclass(frozen=True)
class DynamicTypingBudget:
    maximum_any_references: int
    maximum_type_ignores: int


@dataclass(frozen=True)
class StaticAnalysisBaseline:
    scope: tuple[str, ...]
    tools: tuple[ToolBudget, ...]
    dynamic_typing: DynamicTypingBudget


def _mapping(value: object, context: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise StaticAnalysisBaselineError(f"{context}: must be a JSON object")
    return value


def _positive_or_zero(value: object, context: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise StaticAnalysisBaselineError(f"{context}: must be an integer >= 0")
    return value


def _text(value: object, context: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise StaticAnalysisBaselineError(f"{context}: must be a non-blank string")
    return value.strip()


def load_baseline(path: str | Path) -> StaticAnalysisBaseline:
    """Load the one source of truth for static-analysis versions and ceilings."""

    source = Path(path)
    try:
        payload: object = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise StaticAnalysisBaselineError(f"cannot read static-analysis baseline {source}: {error}") from error
    mapping = _mapping(payload, "static-analysis baseline")
    allowed = {"schema_version", "scope", "tools", "dynamic_typing"}
    missing = sorted(allowed - set(mapping))
    unknown = sorted(set(mapping) - allowed)
    if missing or unknown:
        parts: list[str] = []
        if missing:
            parts.append("missing " + ", ".join(missing))
        if unknown:
            parts.append("unknown " + ", ".join(unknown))
        raise StaticAnalysisBaselineError("static-analysis baseline: " + "; ".join(parts))
    if mapping["schema_version"] != 1:
        raise StaticAnalysisBaselineError("static-analysis baseline.schema_version: expected 1")
    raw_scope = mapping["scope"]
    if not isinstance(raw_scope, list) or not raw_scope:
        raise StaticAnalysisBaselineError("static-analysis baseline.scope: must be a non-empty list")
    scope = tuple(_text(item, "static-analysis baseline.scope entry") for item in raw_scope)
    if len(scope) != len(set(scope)):
        raise StaticAnalysisBaselineError("static-analysis baseline.scope: entries must be unique")
    for item in scope:
        if item.startswith("/") or ".." in Path(item).parts or not (ROOT / item).is_dir():
            raise StaticAnalysisBaselineError(
                f"static-analysis baseline.scope: {item!r} must be a repository directory"
            )
    raw_tools = _mapping(mapping["tools"], "static-analysis baseline.tools")
    if set(raw_tools) != {"ruff", "mypy"}:
        raise StaticAnalysisBaselineError("static-analysis baseline.tools: must name exactly ruff and mypy")
    tools: list[ToolBudget] = []
    for name in ("ruff", "mypy"):
        tool = _mapping(raw_tools[name], f"static-analysis baseline.tools.{name}")
        if set(tool) != {"version", "maximum_errors"}:
            raise StaticAnalysisBaselineError(
                f"static-analysis baseline.tools.{name}: expected version and maximum_errors"
            )
        tools.append(
            ToolBudget(
                name=name,
                version=_text(tool["version"], f"static-analysis baseline.tools.{name}.version"),
                maximum_errors=_positive_or_zero(
                    tool["maximum_errors"], f"static-analysis baseline.tools.{name}.maximum_errors"
                ),
            )
        )
    dynamic = _mapping(mapping["dynamic_typing"], "static-analysis baseline.dynamic_typing")
    if set(dynamic) != {"maximum_any_references", "maximum_type_ignores"}:
        raise StaticAnalysisBaselineError(
            "static-analysis baseline.dynamic_typing: expected maximum_any_references and maximum_type_ignores"
        )
    return StaticAnalysisBaseline(
        scope=scope,
        tools=tuple(tools),
        dynamic_typing=DynamicTypingBudget(
            maximum_any_references=_positive_or_zero(
                dynamic["maximum_any_references"],
                "static-analysis baseline.dynamic_typing.maximum_any_references",
            ),
            maximum_type_ignores=_positive_or_zero(
                dynamic["maximum_type_ignores"],
                "static-analysis baseline.dynamic_typing.maximum_type_ignores",
            ),
        ),
    )


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            command,
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
    except OSError as error:
        raise StaticAnalysisBaselineError(f"cannot run {command[0]!r}: {error}") from error
    if result.returncode not in {0, 1}:
        raise StaticAnalysisBaselineError(
            f"{command[0]} failed to run (exit {result.returncode}): {result.stdout.strip()}"
        )
    return result


def _assert_tool_version(tool: ToolBudget) -> None:
    result = _run([tool.name, "--version"])
    if tool.version not in result.stdout:
        raise StaticAnalysisBaselineError(
            f"{tool.name} version drift: expected {tool.version}, got {result.stdout.strip()!r}"
        )


def ruff_error_count(scope: Iterable[str]) -> int:
    """Return Ruff diagnostics using its stable JSON output rather than text layout."""

    result = _run(["ruff", "check", "--output-format", "json", *scope])
    try:
        diagnostics: object = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise StaticAnalysisBaselineError(f"ruff did not produce JSON diagnostics: {result.stdout}") from error
    if not isinstance(diagnostics, list):
        raise StaticAnalysisBaselineError("ruff diagnostics: expected a JSON list")
    return len(diagnostics)


def mypy_error_count(scope: Iterable[str]) -> int:
    """Return only mypy errors; notes and summaries are deliberately not debt count."""

    result = _run(
        ["mypy", "--warn-unused-ignores", "--show-error-codes", "--no-error-summary", *scope]
    )
    return len(ERROR.findall(result.stdout))


def dynamic_typing_counts(scope: Iterable[str]) -> tuple[int, int]:
    """Count actual ``Any`` references and ``# type: ignore`` nodes in the scoped AST.

    The metric excludes prose, strings, and an import that merely makes ``Any``
    available. It counts annotation/runtime names written as ``Any`` plus
    ``typing.Any`` attributes, and it relies on Python's AST for
    type-ignore comments so a comment in a Markdown/docstring cannot move the budget.
    """

    any_references = 0
    type_ignores = 0
    for relative in scope:
        for source in sorted((ROOT / relative).rglob("*.py")):
            try:
                tree = ast.parse(
                    source.read_text(encoding="utf-8"), filename=str(source), type_comments=True
                )
            except (OSError, SyntaxError, UnicodeDecodeError) as error:
                raise StaticAnalysisBaselineError(
                    f"cannot parse {source.relative_to(ROOT)} while counting dynamic typing: {error}"
                ) from error
            any_references += sum(
                isinstance(node, ast.Name) and node.id == "Any" for node in ast.walk(tree)
            )
            any_references += sum(
                isinstance(node, ast.Attribute) and node.attr == "Any" for node in ast.walk(tree)
            )
            type_ignores += len(tree.type_ignores)
    return any_references, type_ignores


def verify(baseline: StaticAnalysisBaseline) -> tuple[bool, tuple[str, ...]]:
    """Run each check and return every regression rather than stopping at the first."""

    issues: list[str] = []
    for tool in baseline.tools:
        _assert_tool_version(tool)
        actual = ruff_error_count(baseline.scope) if tool.name == "ruff" else mypy_error_count(baseline.scope)
        print(f"{tool.name}: errors={actual} ceiling={tool.maximum_errors}")
        if actual > tool.maximum_errors:
            issues.append(f"{tool.name}: errors {actual} exceed ceiling {tool.maximum_errors}")
    any_references, type_ignores = dynamic_typing_counts(baseline.scope)
    budget = baseline.dynamic_typing
    print(
        "dynamic typing: "
        f"Any={any_references} ceiling={budget.maximum_any_references}; "
        f"type_ignores={type_ignores} ceiling={budget.maximum_type_ignores}"
    )
    if any_references > budget.maximum_any_references:
        issues.append(
            f"dynamic typing: Any references {any_references} exceed ceiling {budget.maximum_any_references}"
        )
    if type_ignores > budget.maximum_type_ignores:
        issues.append(
            f"dynamic typing: type ignores {type_ignores} exceed ceiling {budget.maximum_type_ignores}"
        )
    return not issues, tuple(issues)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    args = parser.parse_args(argv)
    try:
        baseline = load_baseline(args.baseline)
        passed, issues = verify(baseline)
    except StaticAnalysisBaselineError as error:
        print(str(error), file=sys.stderr)
        return 2
    for issue in issues:
        print(issue, file=sys.stderr)
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
