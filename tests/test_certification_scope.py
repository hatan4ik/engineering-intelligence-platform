"""A certification scope is an identity, and it must be sensitive to every material input."""
from __future__ import annotations

import pytest

from resilience.scope import CertificationScope


def scope(**overrides) -> CertificationScope:
    fields = {
        "service": "payments",
        "environment": "prod",
        "runbook_id": "aks.rollout.undo",
        "blast_radius_budget": 2,
    }
    fields.update(overrides)
    return CertificationScope(**fields)


INPUTS = {
    "runbook_definition": {"id": "aks.rollout.undo", "max_blast_radius": 2},
    "policy_bundle_version": "eip-remediation-v1",
    "verification_signal": "deployment.available",
    "dependencies": ("aks-cluster", "prometheus"),
}


def test_scope_hash_is_a_stable_sha256_over_the_canonical_scope():
    first = scope().scope_hash()
    assert first == scope().scope_hash()
    assert len(first) == 64 and set(first) <= set("0123456789abcdef")


@pytest.mark.parametrize(
    "override",
    [
        {"service": "billing"},
        {"environment": "stage"},
        {"runbook_id": "aks.restart.crashloop"},
        {"blast_radius_budget": 3},
    ],
)
def test_every_scope_field_changes_the_scope_hash(override):
    assert scope().scope_hash() != scope(**override).scope_hash()


def test_a_scope_must_name_a_service_environment_runbook_and_a_bounded_budget():
    for override in ({"service": " "}, {"environment": ""}, {"runbook_id": "  "}):
        with pytest.raises(ValueError):
            scope(**override)
    with pytest.raises(ValueError):
        scope(blast_radius_budget=0)


def test_material_inputs_hash_is_stable_for_identical_inputs():
    assert scope().material_inputs_hash(**INPUTS) == scope().material_inputs_hash(**INPUTS)


@pytest.mark.parametrize(
    "override",
    [
        {"runbook_definition": {"id": "aks.rollout.undo", "max_blast_radius": 3}},
        {"policy_bundle_version": "eip-remediation-v2"},
        {"verification_signal": "deployment.progressing"},
        {"dependencies": ("aks-cluster",)},
    ],
)
def test_every_material_input_changes_the_inputs_hash(override):
    changed = {**INPUTS, **override}
    assert scope().material_inputs_hash(**INPUTS) != scope().material_inputs_hash(**changed)


def test_the_inputs_hash_is_bound_to_the_scope():
    assert scope().material_inputs_hash(**INPUTS) != scope(environment="stage").material_inputs_hash(**INPUTS)


def test_dependency_order_is_not_a_material_change():
    reordered = {**INPUTS, "dependencies": ("prometheus", "aks-cluster")}
    assert scope().material_inputs_hash(**INPUTS) == scope().material_inputs_hash(**reordered)


def test_the_evidence_scope_is_the_registry_scope_string():
    assert scope().evidence_scope() == "payments/prod/aks.rollout.undo"
