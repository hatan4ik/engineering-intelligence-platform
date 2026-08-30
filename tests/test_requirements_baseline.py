"""The traceability baseline is machine-checked and does not drift from its view."""

import json

from scripts.verify_requirements_baseline import (
    DEFAULT_BASELINE,
    DEFAULT_VIEW,
    check_rendered_view,
    load_baseline,
    validate_baseline,
)


def test_checked_in_requirements_baseline_has_valid_paths_and_owners():
    requirements = load_baseline()

    assert len(requirements) >= 10
    assert validate_baseline(requirements) == []


def test_markdown_view_is_the_current_rendering_of_the_json_baseline():
    assert check_rendered_view(DEFAULT_VIEW, load_baseline()) is None


def test_validator_rejects_a_missing_implementation_reference(tmp_path):
    payload = json.loads(DEFAULT_BASELINE.read_text(encoding="utf-8"))
    payload["requirements"][0]["implemented_by"] = ["missing/module.py"]
    baseline = tmp_path / "baseline.json"
    baseline.write_text(json.dumps(payload), encoding="utf-8")

    errors = validate_baseline(load_baseline(baseline))

    assert any("missing/module.py" in error for error in errors)
