"""The offline certifier: it only ever writes a record a real scope has earned."""
from __future__ import annotations

import json

import pytest

from remediation.catalog import default_catalog
from resilience.certification import (
    ATTESTED_CONTROLS,
    L4_EVIDENCE_DECISION,
    L4CertificationRecord,
    material_inputs_hash_for,
)
from resilience.exercises import ExerciseKind
from resilience.scope import CertificationScope
from scripts.certify_l4_scope import main


SCOPE = CertificationScope(
    service="payments", environment="prod", runbook_id="aks.rollout.undo", blast_radius_budget=3
)
BUNDLE = "eip-remediation-v1"


def write_exercises(path, *, grade="cluster-exercise", drop=(), passed=True):
    exercises = [
        {
            "kind": kind.value,
            "passed": passed,
            "service": "payments",
            "environment": "prod",
            "runbook_id": "aks.rollout.undo",
            "observed_blast_radius": 2,
            "evidence_ref": f"https://ci.example.invalid/{kind.value}",
            "evidence_grade": grade,
        }
        for kind in ExerciseKind
        if kind not in drop
    ]
    path.write_text(json.dumps({"runner": "kubectl", "exercises": exercises}), encoding="utf-8")
    return path


def write_evidence(directory, *, controls=ATTESTED_CONTROLS, basis="measured"):
    directory.mkdir(parents=True, exist_ok=True)
    for control in controls:
        (directory / f"l4-{control}.json").write_text(json.dumps({
            "evidence_id": f"l4-{control}",
            "scope": "payments/prod/aks.rollout.undo",
            "change": "L4 promotion for the payments rollout-undo scope",
            "claim": f"{control} completed for this scope",
            "method": "independent review",
            "result": "pass",
            "independence": "reviewed outside the platform team",
            "artifacts": ["https://example.invalid/artifact"],
            "approval": "security@example.invalid",
            "basis": basis,
            "decision": L4_EVIDENCE_DECISION,
            "source_run_url": "https://example.invalid/run/1",
        }), encoding="utf-8")
    return directory


def argv(tmp_path, **overrides) -> list[str]:
    args = {
        "--exercises": str(tmp_path / "exercises.json"),
        "--evidence-dir": str(tmp_path / "evidence"),
        "--service": "payments",
        "--environment": "prod",
        "--runbook": "aks.rollout.undo",
        "--blast-radius-budget": "3",
        "--policy-bundle-version": BUNDLE,
        "--issued-by": "security@example.invalid",
        "--output-dir": str(tmp_path / "out"),
    }
    args.update(overrides)
    return [item for pair in args.items() for item in pair]


def record_path(tmp_path):
    return tmp_path / "out" / f"l4-certification-{SCOPE.scope_hash()}.json"


def test_a_complete_scope_produces_a_signed_record(tmp_path, capsys):
    write_exercises(tmp_path / "exercises.json")
    write_evidence(tmp_path / "evidence")
    assert main(argv(tmp_path)) == 0

    payload = json.loads(record_path(tmp_path).read_text(encoding="utf-8"))
    record = L4CertificationRecord.from_dict(payload)
    assert record.scope == SCOPE
    assert record.scope_hash == SCOPE.scope_hash()
    assert record.inputs_hash == material_inputs_hash_for(
        SCOPE, default_catalog().get("aks.rollout.undo"), policy_bundle_version=BUNDLE
    )
    assert record.issued_by == "security@example.invalid"
    assert record.expires_on > record.issued_on
    assert sorted(record.evidence_ids) == sorted(f"l4-{c}" for c in ATTESTED_CONTROLS)
    assert record.exercises_digest.startswith("sha256:")


def test_a_rehearsal_suite_never_certifies_anything(tmp_path, capsys):
    write_exercises(tmp_path / "exercises.json", grade="rehearsal")
    write_evidence(tmp_path / "evidence")
    assert main(argv(tmp_path)) == 1
    out = capsys.readouterr().out
    assert "rehearsal-graded-exercises-excluded" in out
    assert not record_path(tmp_path).exists()


def test_a_missing_exercise_is_reported_and_nothing_is_written(tmp_path, capsys):
    write_exercises(tmp_path / "exercises.json", drop=(ExerciseKind.KILL_SWITCH,))
    write_evidence(tmp_path / "evidence")
    assert main(argv(tmp_path)) == 1
    assert "kill-switch-exercised" in capsys.readouterr().out
    assert not record_path(tmp_path).exists()


def test_an_empty_evidence_registry_is_not_a_certification(tmp_path, capsys):
    write_exercises(tmp_path / "exercises.json")
    write_evidence(tmp_path / "evidence", controls=())
    assert main(argv(tmp_path)) == 1
    out = capsys.readouterr().out
    for control in ATTESTED_CONTROLS:
        assert control in out


def test_the_certifier_refuses_to_write_into_the_evidence_registry(tmp_path, capsys):
    write_exercises(tmp_path / "exercises.json")
    evidence = write_evidence(tmp_path / "docs" / "evidence")
    code = main(argv(
        tmp_path,
        **{"--evidence-dir": str(evidence), "--output-dir": str(evidence)},
    ))
    assert code == 2
    assert "docs/evidence" in capsys.readouterr().out
    assert not (evidence / f"l4-certification-{SCOPE.scope_hash()}.json").exists()


def test_the_platform_may_not_sign_its_own_certification(tmp_path, capsys):
    write_exercises(tmp_path / "exercises.json")
    write_evidence(tmp_path / "evidence")
    assert main(argv(tmp_path, **{"--issued-by": "github-actions"})) == 2
    assert "cannot self-certify" in capsys.readouterr().out
    assert not record_path(tmp_path).exists()


def test_an_unknown_runbook_is_rejected_before_anything_is_read(tmp_path, capsys):
    assert main(argv(tmp_path, **{"--runbook": "not.a.runbook"})) == 2
    assert "not.a.runbook" in capsys.readouterr().out


def test_a_missing_exercises_file_is_reported(tmp_path, capsys):
    write_evidence(tmp_path / "evidence")
    assert main(argv(tmp_path)) == 2
    assert "exercises" in capsys.readouterr().out.lower()


def test_the_record_the_certifier_writes_is_the_one_the_executor_accepts(tmp_path):
    """End to end: certify a scope, then execute at L4 with the record it wrote."""

    from datetime import datetime, timezone

    from remediation.catalog import AutonomyLevel
    from remediation.executor import execute_control_loop
    from remediation.opa_policy import LocalReferenceEvaluator
    from remediation.policy import ActionRequest, ServiceAutonomy

    write_exercises(tmp_path / "exercises.json")
    write_evidence(tmp_path / "evidence")
    assert main(argv(tmp_path, **{"--policy-bundle-version": "local-reference"})) == 0
    record = L4CertificationRecord.from_dict(
        json.loads(record_path(tmp_path).read_text(encoding="utf-8"))
    )

    class Adapter:
        def execute(self, runbook_id, request): return "exec"
        def verify(self, signal, request): return True
        def rollback(self, rollback_id, request): return "rollback"

    result = execute_control_loop(
        catalog=default_catalog(),
        policy=ServiceAutonomy(
            "payments", "prod", AutonomyLevel.BOUNDED_AUTONOMOUS, ("aks.rollout.undo",), 3
        ),
        request=ActionRequest("payments", "prod", "aks.rollout.undo", 2, error_budget_remaining=1.0),
        adapter=Adapter(),
        evaluator=LocalReferenceEvaluator(),
        approval_verified=True,
        certification=record,
        autonomy_level=AutonomyLevel.BOUNDED_AUTONOMOUS,
        now=datetime.now(timezone.utc),
    )
    assert result.status == "succeeded"
