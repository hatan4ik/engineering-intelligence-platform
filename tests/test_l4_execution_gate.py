"""The mutation boundary refuses L4 without a matching, unexpired certification.

The refusal matrix is: no record / expired / wrong scope / changed material
inputs / kill switch / valid. Nothing below L3 changes.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

import pytest

from remediation.catalog import AutonomyLevel, Runbook, RunbookCatalog, default_catalog
from remediation.executor import execute_control_loop
from remediation.opa_policy import LocalReferenceEvaluator
from remediation.policy import ActionRequest, ServiceAutonomy
from resilience.certification import (
    L4CertificationRecord,
    certification_scope_for,
    material_inputs_hash_for,
)


NOW = datetime(2026, 8, 26, tzinfo=timezone.utc)
RUNBOOK_ID = "aks.rollout.undo"
LOCAL_REVISION = "local-reference"


class Adapter:
    def __init__(self) -> None:
        self.executed: list[str] = []

    def execute(self, runbook_id: str, request: ActionRequest) -> str:
        self.executed.append(runbook_id)
        return f"exec-{runbook_id}"

    def verify(self, signal: str, request: ActionRequest) -> bool:
        return True

    def rollback(self, rollback_id: str, request: ActionRequest) -> str:
        return f"rollback-{rollback_id}"


def policy(level: AutonomyLevel = AutonomyLevel.BOUNDED_AUTONOMOUS, *, runbook_id=RUNBOOK_ID):
    return ServiceAutonomy(
        service="payments",
        environment="prod",
        level=level,
        certified_runbooks=(runbook_id,),
        max_blast_radius=5,
        kill_switch=False,
    )


def request(runbook_id: str = RUNBOOK_ID) -> ActionRequest:
    return ActionRequest(
        service="payments",
        environment="prod",
        runbook_id=runbook_id,
        blast_radius=2,
        error_budget_remaining=1.0,
    )


def record(catalog=None, **overrides) -> L4CertificationRecord:
    catalog = catalog or default_catalog()
    runbook = catalog.get(RUNBOOK_ID)
    scope = certification_scope_for(policy=policy(), request=request(), runbook=runbook)
    fields = {
        "scope": scope,
        "scope_hash": scope.scope_hash(),
        "inputs_hash": material_inputs_hash_for(
            scope, runbook, policy_bundle_version=LOCAL_REVISION
        ),
        "exercises_digest": "sha256:cafe",
        "issued_on": "2026-08-01T00:00:00+00:00",
        "expires_on": "2026-11-01T00:00:00+00:00",
        "issued_by": "security@example.invalid",
        "evidence_ids": ("l4-security-review",),
    }
    fields.update(overrides)
    return L4CertificationRecord(**fields)


def run(adapter, *, certification=None, level=AutonomyLevel.BOUNDED_AUTONOMOUS, catalog=None, **kwargs):
    return execute_control_loop(
        catalog=catalog or default_catalog(),
        policy=policy(level),
        request=request(),
        adapter=adapter,
        evaluator=LocalReferenceEvaluator(),
        approval_verified=True,
        certification=certification,
        autonomy_level=level,
        now=NOW,
        **kwargs,
    )


def test_a_matching_unexpired_certification_allows_the_l4_mutation():
    adapter = Adapter()
    result = run(adapter, certification=record())
    assert result.status == "succeeded"
    assert adapter.executed == [RUNBOOK_ID]


def test_l4_without_any_certification_is_blocked_before_the_mutation():
    adapter = Adapter()
    result = run(adapter)
    assert result.status == "blocked"
    assert "no certification record" in result.policy.reason
    assert result.policy.reason.startswith("l4-certification:")
    assert adapter.executed == []


def test_an_expired_certification_is_blocked():
    adapter = Adapter()
    result = run(adapter, certification=record(expires_on="2026-08-25T00:00:00+00:00"))
    assert result.status == "blocked"
    assert "expired" in result.policy.reason
    assert adapter.executed == []


def test_a_certification_for_another_scope_is_blocked():
    adapter = Adapter()
    result = run(adapter, certification=record(scope_hash="0" * 64))
    assert result.status == "blocked"
    assert "scope_hash" in result.policy.reason
    assert adapter.executed == []


def test_a_changed_verification_signal_invalidates_the_certification():
    """A material input changed, so the prior assurance no longer applies."""

    catalog = default_catalog()
    certification = record(catalog)
    changed = RunbookCatalog()
    for runbook_id in catalog.ids():
        runbook = catalog.get(runbook_id)
        if runbook.id == RUNBOOK_ID:
            runbook = replace(runbook, verify_signal="deployment.something_else")
        changed.register(runbook)

    adapter = Adapter()
    result = run(adapter, certification=certification, catalog=changed)
    assert result.status == "blocked"
    assert "material inputs changed" in result.policy.reason
    assert "recertification" in result.policy.reason
    assert adapter.executed == []


def test_a_changed_blast_radius_budget_invalidates_the_certification():
    adapter = Adapter()
    result = execute_control_loop(
        catalog=default_catalog(),
        policy=replace(policy(), max_blast_radius=9),
        request=request(),
        adapter=adapter,
        evaluator=LocalReferenceEvaluator(),
        approval_verified=True,
        certification=record(),
        autonomy_level=AutonomyLevel.BOUNDED_AUTONOMOUS,
        now=NOW,
    )
    assert result.status == "blocked"
    assert "scope_hash" in result.policy.reason
    assert adapter.executed == []


def test_a_service_policy_without_a_bounded_budget_can_never_be_certified():
    adapter = Adapter()
    result = execute_control_loop(
        catalog=default_catalog(),
        policy=replace(policy(), max_blast_radius=0),
        request=replace(request(), blast_radius=0),
        adapter=adapter,
        evaluator=LocalReferenceEvaluator(),
        approval_verified=True,
        certification=record(),
        autonomy_level=AutonomyLevel.BOUNDED_AUTONOMOUS,
        now=NOW,
    )
    assert result.status == "blocked"
    assert result.policy.reason.startswith("l4-certification:")
    assert adapter.executed == []


@pytest.mark.parametrize(
    "level", [AutonomyLevel.APPROVE_AND_EXECUTE, AutonomyLevel.BOUNDED_AUTONOMOUS]
)
def test_the_kill_switch_refuses_every_l3_and_l4_execution(level, monkeypatch):
    monkeypatch.setenv("EIP_AUTONOMY_KILL_SWITCH", "true")
    adapter = Adapter()
    result = run(adapter, certification=record(), level=level)
    assert result.status == "blocked"
    assert result.policy.reason == "kill-switch"
    assert adapter.executed == []


def test_the_kill_switch_engages_on_any_casing_and_is_otherwise_off(monkeypatch):
    """A kill switch errs towards engaged, never towards missing an operator's intent."""

    monkeypatch.setenv("EIP_AUTONOMY_KILL_SWITCH", "TRUE")
    assert run(Adapter(), certification=record()).status == "blocked"
    monkeypatch.setenv("EIP_AUTONOMY_KILL_SWITCH", " true ")
    assert run(Adapter(), certification=record()).status == "blocked"
    monkeypatch.setenv("EIP_AUTONOMY_KILL_SWITCH", "false")
    assert run(Adapter(), certification=record()).status == "succeeded"
    monkeypatch.setenv("EIP_AUTONOMY_KILL_SWITCH", "")
    assert run(Adapter(), certification=record()).status == "succeeded"
    monkeypatch.delenv("EIP_AUTONOMY_KILL_SWITCH")
    assert run(Adapter(), certification=record()).status == "succeeded"


def test_temporal_mode_never_falls_back_to_the_local_policy_evaluator():
    adapter = Adapter()
    result = execute_control_loop(
        catalog=default_catalog(),
        policy=policy(),
        request=request(),
        adapter=adapter,
        evaluator=None,
        approval_verified=True,
        certification=record(),
        autonomy_level=AutonomyLevel.BOUNDED_AUTONOMOUS,
        now=NOW,
        environ={"EIP_CONTROL_PLANE_MODE": "temporal", "EIP_REQUIRE_OPA": "false"},
    )

    assert result.status == "denied"
    assert result.policy.reason == "OPA policy evaluator is required but not configured"
    assert adapter.executed == []


def l2_catalog() -> RunbookCatalog:
    catalog = RunbookCatalog()
    catalog.register(Runbook(
        id="ops.collect.diagnostics",
        description="Collect diagnostics for a human operator",
        environments=("prod",),
        max_blast_radius=5,
        reversible=True,
        required_level=AutonomyLevel.HUMAN_EXECUTE,
        verify_signal="diagnostics.collected",
    ))
    return catalog


def test_l0_to_l2_paths_are_unchanged_by_the_gate_and_the_kill_switch(monkeypatch):
    monkeypatch.setenv("EIP_AUTONOMY_KILL_SWITCH", "true")
    adapter = Adapter()
    result = execute_control_loop(
        catalog=l2_catalog(),
        policy=policy(AutonomyLevel.HUMAN_EXECUTE, runbook_id="ops.collect.diagnostics"),
        request=request("ops.collect.diagnostics"),
        adapter=adapter,
        evaluator=LocalReferenceEvaluator(),
        now=NOW,
    )
    assert result.status == "succeeded"
    assert adapter.executed == ["ops.collect.diagnostics"]


def test_the_autonomy_level_defaults_to_the_reviewed_service_policy_level():
    """A caller that does not declare a level is still gated at the policy's level."""

    adapter = Adapter()
    result = execute_control_loop(
        catalog=default_catalog(),
        policy=policy(),
        request=request(),
        adapter=adapter,
        evaluator=LocalReferenceEvaluator(),
        approval_verified=True,
        now=NOW,
    )
    assert result.status == "blocked"
    assert result.policy.reason.startswith("l4-certification:")
    assert adapter.executed == []


def test_a_policy_denial_still_reports_the_policy_reason_not_the_gate():
    adapter = Adapter()
    result = execute_control_loop(
        catalog=default_catalog(),
        policy=policy(),
        request=replace(request(), error_budget_remaining=0.0),
        adapter=adapter,
        evaluator=LocalReferenceEvaluator(),
        approval_verified=True,
        certification=record(),
        autonomy_level=AutonomyLevel.BOUNDED_AUTONOMOUS,
        now=NOW,
    )
    assert result.status == "denied"
    assert "error budget exhausted" in result.policy.reason
    assert adapter.executed == []


# --- the declared level is a claim, not an authority --------------------------


def diverge(*, policy_level, declared, certification=None, adapter=None):
    adapter = adapter or Adapter()
    result = execute_control_loop(
        catalog=default_catalog(),
        policy=policy(policy_level),
        request=request(),
        adapter=adapter,
        evaluator=LocalReferenceEvaluator(),
        approval_verified=True,
        certification=certification,
        autonomy_level=declared,
        now=NOW,
    )
    return result, adapter


@pytest.mark.parametrize(
    "policy_level,declared",
    [
        (AutonomyLevel.BOUNDED_AUTONOMOUS, AutonomyLevel.OBSERVE),
        (AutonomyLevel.BOUNDED_AUTONOMOUS, AutonomyLevel.RECOMMEND),
        (AutonomyLevel.BOUNDED_AUTONOMOUS, AutonomyLevel.HUMAN_EXECUTE),
        (AutonomyLevel.APPROVE_AND_EXECUTE, AutonomyLevel.OBSERVE),
        (AutonomyLevel.APPROVE_AND_EXECUTE, AutonomyLevel.RECOMMEND),
        (AutonomyLevel.APPROVE_AND_EXECUTE, AutonomyLevel.HUMAN_EXECUTE),
        (AutonomyLevel.HUMAN_EXECUTE, AutonomyLevel.OBSERVE),
        (AutonomyLevel.HUMAN_EXECUTE, AutonomyLevel.RECOMMEND),
    ],
)
def test_an_unsanctioned_downgrade_is_refused_and_names_both_levels(policy_level, declared):
    result, adapter = diverge(policy_level=policy_level, declared=declared)
    assert result.status == "blocked"
    assert result.policy.reason.startswith("autonomy-level:")
    assert f"L{int(declared)}" in result.policy.reason
    assert f"L{int(policy_level)}" in result.policy.reason
    assert adapter.executed == []


def test_a_declared_l2_can_no_longer_execute_an_uncertified_l4_mutation():
    """The reported bypass: declaring a low level must not skip the L4 gate."""

    result, adapter = diverge(
        policy_level=AutonomyLevel.BOUNDED_AUTONOMOUS,
        declared=AutonomyLevel.HUMAN_EXECUTE,
        certification=None,
    )
    assert result.status == "blocked"
    assert adapter.executed == []


def test_a_declared_l2_cannot_escape_the_kill_switch(monkeypatch):
    monkeypatch.setenv("EIP_AUTONOMY_KILL_SWITCH", "true")
    result, adapter = diverge(
        policy_level=AutonomyLevel.BOUNDED_AUTONOMOUS,
        declared=AutonomyLevel.HUMAN_EXECUTE,
        certification=record(),
    )
    assert result.status == "blocked"
    assert result.policy.reason == "kill-switch"
    assert adapter.executed == []


@pytest.mark.parametrize(
    "policy_level,declared",
    [
        (AutonomyLevel.HUMAN_EXECUTE, AutonomyLevel.APPROVE_AND_EXECUTE),
        (AutonomyLevel.HUMAN_EXECUTE, AutonomyLevel.BOUNDED_AUTONOMOUS),
        (AutonomyLevel.APPROVE_AND_EXECUTE, AutonomyLevel.BOUNDED_AUTONOMOUS),
    ],
)
def test_a_declared_level_above_the_reviewed_policy_is_refused(policy_level, declared):
    result, adapter = diverge(
        policy_level=policy_level, declared=declared, certification=record()
    )
    assert result.status == "blocked"
    assert result.policy.reason.startswith("autonomy-level:")
    assert f"L{int(declared)}" in result.policy.reason
    assert f"L{int(policy_level)}" in result.policy.reason
    assert adapter.executed == []


def test_the_one_permitted_downgrade_runs_an_l4_scope_as_a_supervised_l3():
    """The exercise path: an L4-policy request run as a supervised L3 run."""

    result, adapter = diverge(
        policy_level=AutonomyLevel.BOUNDED_AUTONOMOUS,
        declared=AutonomyLevel.APPROVE_AND_EXECUTE,
        certification=None,
    )
    assert result.status == "succeeded"
    assert adapter.executed == [RUNBOOK_ID]


def test_the_permitted_downgrade_does_not_escape_the_kill_switch(monkeypatch):
    monkeypatch.setenv("EIP_AUTONOMY_KILL_SWITCH", "true")
    result, adapter = diverge(
        policy_level=AutonomyLevel.BOUNDED_AUTONOMOUS,
        declared=AutonomyLevel.APPROVE_AND_EXECUTE,
    )
    assert result.status == "blocked"
    assert result.policy.reason == "kill-switch"
    assert adapter.executed == []


def test_the_policy_boundary_is_told_the_effective_level_not_the_declared_one():
    seen: dict = {}

    class Recorder(LocalReferenceEvaluator):
        def evaluate(self, **kwargs):
            seen.update(kwargs)
            return super().evaluate(**kwargs)

    execute_control_loop(
        catalog=default_catalog(),
        policy=policy(AutonomyLevel.BOUNDED_AUTONOMOUS),
        request=request(),
        adapter=Adapter(),
        evaluator=Recorder(),
        approval_verified=True,
        certification=record(),
        autonomy_level=AutonomyLevel.BOUNDED_AUTONOMOUS,
        now=NOW,
    )
    assert seen["autonomy"].autonomy_level == "L4"
    assert seen["autonomy"].policy_level == int(AutonomyLevel.BOUNDED_AUTONOMOUS)


def test_a_declared_level_that_is_not_a_level_at_all_is_refused():
    result, adapter = diverge(
        policy_level=AutonomyLevel.BOUNDED_AUTONOMOUS, declared=42, certification=record()
    )
    assert result.status == "blocked"
    assert result.policy.reason.startswith("autonomy-level:")
    assert adapter.executed == []


def test_an_over_declaration_with_the_switch_engaged_reports_the_kill_switch(monkeypatch):
    """The switch keys off the raw claim, so it outranks the level refusal."""

    monkeypatch.setenv("EIP_AUTONOMY_KILL_SWITCH", "true")
    result, adapter = diverge(
        policy_level=AutonomyLevel.HUMAN_EXECUTE,
        declared=AutonomyLevel.BOUNDED_AUTONOMOUS,
        certification=record(),
    )
    assert result.status == "blocked"
    assert result.policy.reason == "kill-switch"
    assert adapter.executed == []


def test_an_uninterpretable_over_declaration_still_hits_the_kill_switch(monkeypatch):
    monkeypatch.setenv("EIP_AUTONOMY_KILL_SWITCH", "true")
    result, adapter = diverge(policy_level=AutonomyLevel.HUMAN_EXECUTE, declared=42)
    assert result.status == "blocked"
    assert result.policy.reason == "kill-switch"
    assert adapter.executed == []


def test_an_l2_policy_with_an_l2_claim_is_untouched_by_the_switch(monkeypatch):
    """max() must not lift an honest L2 request into the switch's reach."""

    monkeypatch.setenv("EIP_AUTONOMY_KILL_SWITCH", "true")
    adapter = Adapter()
    result = execute_control_loop(
        catalog=l2_catalog(),
        policy=policy(AutonomyLevel.HUMAN_EXECUTE, runbook_id="ops.collect.diagnostics"),
        request=request("ops.collect.diagnostics"),
        adapter=adapter,
        evaluator=LocalReferenceEvaluator(),
        autonomy_level=AutonomyLevel.HUMAN_EXECUTE,
        now=NOW,
    )
    assert result.status == "succeeded"
    assert adapter.executed == ["ops.collect.diagnostics"]
