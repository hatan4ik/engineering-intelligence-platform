from intelligence.extractors import build_graph, metadata_from_manifest, service_from_path
from intelligence.pr_guardian import policy_for, render_markdown
from intelligence.risk import ChangeContext, assess_change


def test_manifest_metadata_builds_dependency_graph():
    api = metadata_from_manifest(
        "k8s/api.yaml",
        """
metadata:
  labels:
    app: api
    owner: platform
    tier: critical
    dependencies: auth, database
""",
    )
    assert api is not None
    graph = build_graph([api])
    assert "auth" in graph.nodes
    assert "database" in graph.nodes
    assert service_from_path("services/api/main.py", set(graph.nodes)) == "api"
    blast = graph.blast_radius({"auth"})
    assert "api" in blast


def test_pr_guardian_requires_controls_for_high_risk_change():
    graph = build_graph([
        metadata_from_manifest(
            "api.yaml",
            "app: api\ntier: critical\ndependencies: auth, database\n",
        )
    ])
    assessment = assess_change(
        graph,
        ChangeContext(
            changed_services=("api",),
            files_changed=30,
            touches_iac=True,
            touches_identity_or_security=True,
            weak_test_evidence=True,
            similar_failed_changes=2,
        ),
    )
    decision = policy_for(assessment)
    assert decision.require_extended_tests
    assert decision.require_additional_approval
    assert assessment.score >= 70
    rendered = render_markdown(assessment)
    assert "security-boundary-change" in rendered
    assert "Risk score" in rendered
