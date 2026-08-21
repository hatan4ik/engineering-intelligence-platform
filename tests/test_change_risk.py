from intelligence.graph import ServiceGraph, ServiceNode
from intelligence.risk import ChangeContext, assess_change


def graph():
    g = ServiceGraph()
    g.add(ServiceNode("auth", tier=1, owner="identity"))
    g.add(ServiceNode("payments", tier=1, owner="payments", dependencies=("auth",)))
    g.add(ServiceNode("checkout", tier=2, owner="commerce", dependencies=("payments",)))
    g.add(ServiceNode("web", tier=2, owner="frontend", dependencies=("checkout",)))
    return g


def test_blast_radius_walks_reverse_dependencies():
    assert graph().blast_radius({"auth"}) == {"auth", "payments", "checkout", "web"}


def test_security_iac_change_gets_explainable_high_risk():
    result = assess_change(
        graph(),
        ChangeContext(
            changed_services=("auth",),
            files_changed=14,
            touches_iac=True,
            touches_identity_or_security=True,
            weak_test_evidence=True,
            similar_failed_changes=1,
        ),
    )
    assert result.score >= 70
    assert result.band in {"high", "critical"}
    names = {f.name for f in result.factors}
    assert {"critical-service", "security-boundary-change", "infrastructure-change"} <= names
    assert "web" in result.blast_radius
