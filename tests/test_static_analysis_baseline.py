"""Static-analysis debt is a parsed, non-increasing contract."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.verify_static_analysis_baseline import (
    DynamicTypingBudget,
    StaticAnalysisBaseline,
    StaticAnalysisBaselineError,
    ToolBudget,
    dynamic_typing_counts,
    load_baseline,
)


ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "requirements" / "static-analysis-baseline.json"


def test_checked_in_baseline_has_the_expected_core_scope_and_tool_versions():
    baseline = load_baseline(BASELINE)

    assert baseline.scope == (
        "app",
        "company_brain",
        "intelligence",
        "product",
        "remediation",
        "control_plane",
        "state",
    )
    assert [(tool.name, tool.version) for tool in baseline.tools] == [
        ("ruff", "0.16.4"),
        ("mypy", "2.3.1"),
    ]


def test_dynamic_typing_count_uses_python_not_prose_or_comments(tmp_path, monkeypatch):
    source_root = tmp_path / "sample"
    source_root.mkdir()
    (source_root / "example.py").write_text(
        "from typing import Any\n\nvalue: Any = None  # type: ignore[assignment]\ntext = 'Any # type: ignore'\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("scripts.verify_static_analysis_baseline.ROOT", tmp_path)

    assert dynamic_typing_counts(("sample",)) == (1, 1)


def test_baseline_rejects_unknown_or_missing_contract_fields(tmp_path):
    payload = json.loads(BASELINE.read_text(encoding="utf-8"))
    payload["unexpected"] = True
    path = tmp_path / "baseline.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(StaticAnalysisBaselineError, match="unknown unexpected"):
        load_baseline(path)


def test_dynamic_budget_is_an_explicit_part_of_the_contract():
    baseline = StaticAnalysisBaseline(
        scope=("app",),
        tools=(ToolBudget("ruff", "0.16.4", 3), ToolBudget("mypy", "2.3.1", 43)),
        dynamic_typing=DynamicTypingBudget(maximum_any_references=10, maximum_type_ignores=1),
    )

    assert baseline.dynamic_typing.maximum_any_references == 10
    assert baseline.dynamic_typing.maximum_type_ignores == 1
