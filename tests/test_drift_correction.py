from intelligence.drift import DriftFinding, ResourceSnapshot
from intelligence.drift_correction import build_correction_plan, render_correction_markdown
from product.drift_correction_service import DriftCorrectionService


def finding(field: str, desired, observed) -> DriftFinding:
    return DriftFinding(
        resource_id="deploy/payments",
        service="payments",
        environment="prod",
        field=field,
        desired=desired,
        observed=observed,
        evidence="desired-state vs observed-state",
        severity=4,
    )


def test_safe_fields_create_reviewable_configuration_plan():
    plan = build_correction_plan(
        (finding("replicas", 3, 1), finding("image", "app:v2", "app:v1")),
        source_path="deploy/payments.yaml",
        source_revision="abc123",
    )
    assert plan is not None
    assert plan.patchable is True
    assert plan.requires_human_design is False
    body = render_correction_markdown(plan)
    assert "configuration PR" in body
    assert "does **not** authorize a production mutation" in body


def test_security_architecture_fields_never_auto_patch():
    plan = build_correction_plan(
        (finding("identity", "workload-id", "legacy-secret"),),
        source_path="infra/payments.tf",
    )
    assert plan is not None
    assert plan.patchable is False
    assert plan.requires_human_design is True


class Provider:
    def desired(self, *, service: str, environment: str):
        return [
            ResourceSnapshot(
                resource_id="deploy/payments",
                service=service,
                environment=environment,
                desired={"replicas": 3},
                observed={"replicas": 1},
                source="git:deploy/payments.yaml@abc123",
            )
        ]

    def source_location(self, snapshot):
        return "deploy/payments.yaml", "abc123"


class Workflow:
    workflow_id = "wf-drift-1"


class Workflows:
    def start_drift_review(self, **kwargs):
        assert kwargs["resource_id"] == "deploy/payments"
        assert kwargs["findings"]
        return Workflow()


class Publisher:
    def __init__(self):
        self.calls = []

    def publish_plan(self, *, plan, workflow_id):
        self.calls.append((plan, workflow_id))


def test_service_publishes_plan_but_does_not_execute_mutation():
    publisher = Publisher()
    service = DriftCorrectionService(provider=Provider(), workflows=Workflows(), publisher=publisher)
    result = service.run(service="payments", environment="prod")
    assert result.workflow_ids == ("wf-drift-1",)
    assert len(result.plans) == 1
    assert publisher.calls[0][1] == "wf-drift-1"
    assert result.plans[0].source_path == "deploy/payments.yaml"
