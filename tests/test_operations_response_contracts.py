"""The operations API makes its L2 non-execution guarantee structural."""

import pytest
from pydantic import ValidationError

from app.operations.contracts import (
    DeploymentAnalysisResponse,
    DeploymentInvestigationResponse,
    ProposalResponse,
)


def _report_payload() -> dict[str, object]:
    return {
        "correlation_id": "corr-42",
        "workflow_id": "deployment-failure:42",
        "service": "payments",
        "environment": "prod",
        "analysis": DeploymentAnalysisResponse(
            deployment_id="deployment-42",
            service="payments",
            facts=["The deployment failed."],
            hypotheses=[],
            evidence_ids=[],
        ),
        "proposals": [
            ProposalResponse(
                kind="ticket",
                title="Investigate payments",
                exact_action="Open an investigation ticket.",
                rollback_path="Close the ticket if it is a false signal.",
                evidence_refs=[],
                requires_human=True,
            )
        ],
    }


def test_l2_response_defaults_to_and_enforces_non_execution():
    payload = _report_payload()

    assert DeploymentInvestigationResponse(**payload).executed is False

    with pytest.raises(ValidationError, match="executed"):
        DeploymentInvestigationResponse(**payload, executed=True)
