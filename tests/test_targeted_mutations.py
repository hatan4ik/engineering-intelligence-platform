"""The curated mutation contract stays syntactically valid and tied to source."""
from __future__ import annotations

from scripts.verify_targeted_mutations import MUTATIONS, ROOT, mutated_source


def test_every_targeted_mutation_has_one_compilable_source_target():
    identifiers = {case.identifier for case in MUTATIONS}

    assert len(identifiers) == len(MUTATIONS)
    for case in MUTATIONS:
        source = (ROOT / case.target).read_text(encoding="utf-8")
        assert source.count(case.needle) == 1
        assert mutated_source(source, case) != source


def test_targeted_mutations_cover_each_dependency_boundary_safety_control():
    assert {case.identifier for case in MUTATIONS} == {
        "opens-at-failure-threshold",
        "rejects-open-circuit",
        "rejects-bulkhead-overflow",
        "preserves-open-circuit-from-stale-success",
    }
