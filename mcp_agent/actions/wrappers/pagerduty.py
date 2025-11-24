from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List

from mcp_agent.types import ToolInvocationResult

from ._common import _clean_payload, _invoke_mcp_tool, ensure_authorized

if TYPE_CHECKING:
    from mcp_agent.core.context import AgentContext


def pagerduty_create_incident_record(
    context: "AgentContext",
    incident__assignments: List[Any] | None = None,
    incident__body__details: str | None = "Incident details pending",
    incident__body__type: str | None = "Test",
    incident__conference__bridge__conference__number: str | None = None,
    incident__conference__bridge__conference__type: str | None = None,
    incident__conference__bridge__conference__url: str | None = "https://meet.example.com/incident",
    incident__incident__key: str | None = None,
    incident__incident__type__id: str | None = None,
    incident__incident__type__name: str | None = "engineering_incident",
    incident__incident__type__type: str | None = "incident_type_reference",
    incident__priority__id: str | None = None,
    incident__priority__type: str | None = None,
    incident__service__id: str | None = None,
    incident__service__type: str | None = "service_reference",
    incident__title: str | None = "New Incident",
    incident__type: str | None = "incident",
    incident__urgency: str | None = "low",
) -> ToolInvocationResult:
    """
    Create a PagerDuty incident with detailed configuration.
    """
    provider = "pagerduty"
    tool_name = "PAGERDUTY_CREATE_INCIDENT_RECORD"
    ensure_authorized(context, provider)
    payload = _clean_payload(
        {
            "incident__assignments": incident__assignments,
            "incident__body__details": incident__body__details,
            "incident__body__type": incident__body__type,
            "incident__conference__bridge__conference__number": incident__conference__bridge__conference__number,
            "incident__conference__bridge__conference__type": incident__conference__bridge__conference__type,
            "incident__conference__bridge__conference__url": incident__conference__bridge__conference__url,
            "incident__incident__key": incident__incident__key,
            "incident__incident__type__id": incident__incident__type__id,
            "incident__incident__type__name": incident__incident__type__name,
            "incident__incident__type__type": incident__incident__type__type,
            "incident__priority__id": incident__priority__id,
            "incident__priority__type": incident__priority__type,
            "incident__service__id": incident__service__id,
            "incident__service__type": incident__service__type,
            "incident__title": incident__title,
            "incident__type": incident__type,
            "incident__urgency": incident__urgency,
        }
    )
    return _invoke_mcp_tool(context, provider, tool_name, payload)
