from finops.attribution import CostEvent, aggregate_by
from finops.outcomes import EngineeringOutcomes, control_tower


def test_costs_are_attributed_by_service_and_agent():
    events = [
        CostEvent("payments", "repo-a", "pr-guardian", "alice", model_cost_usd=1.2, search_cost_usd=0.3),
        CostEvent("payments", "repo-a", "incident", "bob", model_cost_usd=0.5),
    ]
    assert aggregate_by(events, "service") == {"payments": 2.0}
    assert aggregate_by(events, "agent")["pr-guardian"] == 1.5


def test_control_tower_separates_cost_and_measured_value():
    metrics = control_tower(
        EngineeringOutcomes(
            deployments=100,
            failed_deployments=5,
            incidents=20,
            repeated_incidents=2,
            mttr_minutes=42,
            engineer_hours_saved=200,
            prevented_incidents=3,
            platform_cost_usd=5000,
        ),
        loaded_labor_rate_usd=100,
    )
    assert metrics["change_failure_rate"] == 0.05
    assert metrics["labor_value_usd"] == 20000
    assert metrics["net_value_usd"] == 15000
