"""Normalize external operational events at the HTTP/CLI trust boundary."""

from __future__ import annotations

from typing import Mapping

from .contracts import IncidentTrigger


def normalize_common_alert(payload: Mapping[str, object]) -> IncidentTrigger:
    """Parse an Azure Monitor common alert into an explicit incident scope.

    ``service`` and ``environment`` come from the alert rule's
    ``customProperties``. Azure Monitor has no other reliable carrier for
    those values, and guessing them from resource identifiers would attribute
    evidence to the wrong service.
    """

    data = payload.get("data")
    if not isinstance(data, Mapping):
        raise ValueError("common alert schema payload has no 'data' object")
    essentials = data.get("essentials")
    if not isinstance(essentials, Mapping):
        raise ValueError("common alert schema payload has no 'data.essentials' object")

    raw_id = str(essentials.get("originAlertId") or essentials.get("alertId") or "").strip()
    if not raw_id:
        raise ValueError("common alert schema payload has no alertId")
    incident_id = raw_id.rsplit("/", 1)[-1]

    properties = data.get("customProperties")
    if not isinstance(properties, Mapping):
        raise ValueError("alert is missing data.customProperties.service and .environment")
    missing = [
        name
        for name in ("service", "environment")
        if not str(properties.get(name) or "").strip()
    ]
    if missing:
        raise ValueError("alert customProperties is missing " + ", ".join(missing))

    condition = str(essentials.get("monitorCondition") or "Fired").strip().lower()
    return IncidentTrigger(
        incident_id=incident_id,
        service=str(properties["service"]).strip(),
        environment=str(properties["environment"]).strip(),
        fired=condition == "fired",
    )
