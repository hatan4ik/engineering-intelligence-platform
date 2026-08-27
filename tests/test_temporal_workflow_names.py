"""Every Temporal workflow name is defined exactly once, and only the gated
remediation workflow answers to ``eip.remediation.v1``.

A second class carrying the same name -- for example a stub whose ``run``
returned ``{"status": "completed"}`` without executing the control loop -- would
be indistinguishable from the real one at registration time.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytest.importorskip("temporalio")

from orchestration.remediation_workflow import REMEDIATION_WORKFLOW_NAME, RemediationWorkflow
from orchestration.temporal_worker import worker_registration_plan

ORCHESTRATION = Path(__file__).resolve().parents[1] / "orchestration"

COSMOS_ENABLED = {
    "EIP_CONTROL_PLANE_MODE": "temporal",
    "EIP_COSMOS_ENDPOINT": "https://eip.documents.azure.invalid:443/",
    "EIP_COSMOS_DATABASE": "eip",
    "EIP_COSMOS_STATE_CONTAINER": "workflow-state",
    "EIP_COSMOS_AUDIT_CONTAINER": "workflow-audit",
    "EIP_TEMPORAL_REMEDIATION_WORKFLOWS": "enabled",
}


def _declared_workflow_names() -> dict[str, list[str]]:
    """Map every ``@workflow.defn(name=...)`` literal to the classes declaring it."""

    declared: dict[str, list[str]] = {}
    for module in sorted(ORCHESTRATION.rglob("*.py")):
        tree = ast.parse(module.read_text(encoding="utf-8"), filename=str(module))
        constants = {
            target.id: node.value.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant)
            for target in node.targets
            if isinstance(target, ast.Name)
        }
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            for decorator in node.decorator_list:
                if not isinstance(decorator, ast.Call):
                    continue
                func = decorator.func
                is_defn = (
                    isinstance(func, ast.Attribute)
                    and func.attr == "defn"
                    and isinstance(func.value, ast.Name)
                    and func.value.id == "workflow"
                )
                if not is_defn:
                    continue
                for keyword in decorator.keywords:
                    if keyword.arg != "name":
                        continue
                    value = keyword.value
                    if isinstance(value, ast.Constant):
                        name = str(value.value)
                    elif isinstance(value, ast.Name) and value.id in constants:
                        name = str(constants[value.id])
                    else:  # pragma: no cover - a dynamic name is itself a finding
                        raise AssertionError(f"{module.name}:{node.name} declares a non-literal workflow name")
                    declared.setdefault(name, []).append(f"{module.relative_to(ORCHESTRATION)}::{node.name}")
    return declared


def test_every_temporal_workflow_name_is_declared_exactly_once():
    declared = _declared_workflow_names()
    duplicates = {name: where for name, where in declared.items() if len(where) > 1}
    assert duplicates == {}, f"duplicate Temporal workflow names: {duplicates}"
    assert declared[REMEDIATION_WORKFLOW_NAME] == ["remediation_workflow.py::RemediationWorkflow"]


def test_only_the_gated_class_is_registered_for_the_remediation_name():
    plan = worker_registration_plan(environ=COSMOS_ENABLED)
    remediation_classes = [
        cls for cls in plan.workflows if getattr(cls, "__temporal_workflow_definition", None)
        and cls.__temporal_workflow_definition.name == REMEDIATION_WORKFLOW_NAME
    ]
    assert remediation_classes == [RemediationWorkflow]


def test_the_evidence_module_declares_only_the_evidence_workflow():
    declared = _declared_workflow_names()
    evidence_module = [
        name for name, where in declared.items() if any(w.startswith("temporal_workflow.py::") for w in where)
    ]
    assert evidence_module == ["eip.control-plane-evidence.v1"]
