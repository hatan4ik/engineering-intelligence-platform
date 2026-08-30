"""Static contracts for the deployment-visible safety controls.

Helm itself is linted later in CI. These tests keep the Python/Helm names and
the explicitly restart-required update semantics close to the application
behaviour being protected.
"""
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VALUES = ROOT / "helm" / "eip" / "values.yaml"
DEPLOYMENT = ROOT / "helm" / "eip" / "templates" / "deployment.yaml"


def test_chart_declares_each_process_safety_control():
    values = VALUES.read_text(encoding="utf-8")
    deployment = DEPLOYMENT.read_text(encoding="utf-8")

    for field in (
        "controlPlaneMode:",
        "requireOpa:",
        "autonomyKillSwitch:",
        "prGuardianKillSwitch:",
    ):
        assert field in values
    for variable in (
        "EIP_CONTROL_PLANE_MODE",
        "EIP_REQUIRE_OPA",
        "EIP_AUTONOMY_KILL_SWITCH",
        "EIP_PR_GUARDIAN_KILL_SWITCH",
    ):
        assert f"- name: {variable}" in deployment


def test_chart_documents_restart_required_kill_switch_updates():
    values = VALUES.read_text(encoding="utf-8")

    assert "replacement pod starts" in values
    assert "not a\n# live control-plane API" in values
