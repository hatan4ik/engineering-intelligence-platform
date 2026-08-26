"""The L3 rehearsal runner exercises every certification kind, and says what it is."""
from __future__ import annotations

import json

import pytest

from resilience.exercises import ExerciseKind
from scripts.run_l3_exercises import main, scope_hash


ARGS = [
    "--service", "payments",
    "--environment", "prod",
    "--runbook", "aks.restart.crashloop",
]


def run(tmp_path, *extra: str) -> tuple[int, dict]:
    code = main([*ARGS, "--output-dir", str(tmp_path), *extra])
    path = tmp_path / f"l3-exercises-{scope_hash('payments', 'prod', 'aks.restart.crashloop')}.json"
    return code, (json.loads(path.read_text(encoding="utf-8")) if path.exists() else {})


def test_the_simulated_runner_writes_every_exercise_kind(tmp_path):
    code, report = run(tmp_path)
    assert code == 0
    kinds = [item["kind"] for item in report["exercises"]]
    assert sorted(kinds) == sorted(kind.value for kind in ExerciseKind)


def test_every_simulated_result_is_graded_as_rehearsal(tmp_path):
    _, report = run(tmp_path)
    assert report["runner"] == "simulated"
    assert report["evidence_grade"] == "rehearsal"
    assert all(item["evidence_grade"] == "rehearsal" for item in report["exercises"])


def test_a_simulated_run_states_it_is_not_production_evidence(tmp_path, capsys):
    _, report = run(tmp_path)
    assert report["production_evidence"] is False
    assert "not production evidence" in report["disclaimer"].lower()
    assert report["certification_assessment"] is None
    assert "rehearsal" in capsys.readouterr().out.lower()


def test_the_bounded_control_loop_passes_its_positive_and_fail_closed_exercises(tmp_path):
    _, report = run(tmp_path)
    outcomes = {item["kind"]: item["passed"] for item in report["exercises"]}
    assert outcomes[ExerciseKind.SUCCESSFUL_REMEDIATION.value] is True
    assert outcomes[ExerciseKind.VERIFICATION_FAILURE.value] is True
    assert outcomes[ExerciseKind.KILL_SWITCH.value] is True
    assert outcomes[ExerciseKind.POLICY_OUTAGE.value] is True
    assert outcomes[ExerciseKind.AUDIT_OUTAGE.value] is True


def test_a_runbook_without_a_usable_rollback_fails_its_rollback_exercise(tmp_path):
    _, report = run(tmp_path)
    rollback = next(i for i in report["exercises"] if i["kind"] == ExerciseKind.ROLLBACK.value)
    assert rollback["passed"] is False
    assert "rollback" in rollback["detail"].lower()


def test_a_runbook_with_a_rollback_path_passes_its_rollback_exercise(tmp_path):
    code = main([
        "--service", "payments",
        "--environment", "stage",
        "--runbook", "aks.scale.memory",
        "--output-dir", str(tmp_path),
    ])
    assert code == 0
    path = tmp_path / f"l3-exercises-{scope_hash('payments', 'stage', 'aks.scale.memory')}.json"
    report = json.loads(path.read_text(encoding="utf-8"))
    rollback = next(i for i in report["exercises"] if i["kind"] == ExerciseKind.ROLLBACK.value)
    assert rollback["passed"] is True


def test_the_kubectl_runner_fails_closed_without_cluster_access(tmp_path, monkeypatch):
    monkeypatch.delenv("KUBECONFIG", raising=False)
    monkeypatch.setattr("scripts.run_l3_exercises.shutil.which", lambda name: None)
    with pytest.raises(RuntimeError) as excinfo:
        main([*ARGS, "--runner", "kubectl", "--output-dir", str(tmp_path)])
    message = str(excinfo.value)
    assert "KUBECONFIG" in message
    assert "kubectl" in message


def test_the_kubectl_runner_requires_an_explicit_opa_endpoint(tmp_path, monkeypatch):
    monkeypatch.setenv("KUBECONFIG", str(tmp_path / "kubeconfig"))
    monkeypatch.setattr("scripts.run_l3_exercises.shutil.which", lambda name: "/usr/bin/kubectl")
    with pytest.raises(RuntimeError, match="--opa-endpoint"):
        main([*ARGS, "--runner", "kubectl", "--output-dir", str(tmp_path)])


def test_an_invalid_service_name_is_rejected_before_anything_runs(tmp_path):
    assert main(["--service", "Payments Prod", "--environment", "prod",
                 "--runbook", "aks.restart.crashloop", "--output-dir", str(tmp_path)]) == 2
