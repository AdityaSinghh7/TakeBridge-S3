from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List

from mcp_agent.types import ToolInvocationResult

from ._common import _clean_payload, _invoke_mcp_tool, ensure_authorized

if TYPE_CHECKING:
    from mcp_agent.core.context import AgentContext


def klaviyo_create_campaign(
    context: "AgentContext",
    data__attributes__audiences__excluded: List[Any] | None = None,
    data__attributes__audiences__included: List[Any] | None = None,
    data__attributes__campaign__messages__data: List[Any] | None = None,
    data__attributes__name: str | None = None,
    data__attributes__send__options: Dict[str, Any] | None = None,
    data__attributes__send__strategy__method: str | None = None,
    data__attributes__send__strategy__options__static__datetime: str | None = None,
    data__attributes__send__strategy__options__static__is__local: bool | None = None,
    data__attributes__send__strategy__options__static__send__past__recipients__immediately: bool | None = None,
    data__attributes__send__strategy__options__sto__date: str | None = None,
    data__attributes__send__strategy__options__throttled__datetime: str | None = None,
    data__attributes__send__strategy__options__throttled__throttle__percentage: int | None = None,
    data__attributes__tracking__options: Dict[str, Any] | None = None,
    data__type: str | None = None,
) -> ToolInvocationResult:
    """
    Create a Klaviyo campaign with the provided parameters.
    """
    provider = "klaviyo"
    tool_name = "KLAVIYO_CREATE_CAMPAIGN"
    ensure_authorized(context, provider)
    payload = _clean_payload(
        {
            "data__attributes__audiences__excluded": data__attributes__audiences__excluded,
            "data__attributes__audiences__included": data__attributes__audiences__included,
            "data__attributes__campaign__messages__data": data__attributes__campaign__messages__data,
            "data__attributes__name": data__attributes__name,
            "data__attributes__send__options": data__attributes__send__options,
            "data__attributes__send__strategy__method": data__attributes__send__strategy__method,
            "data__attributes__send__strategy__options__static__datetime": data__attributes__send__strategy__options__static__datetime,
            "data__attributes__send__strategy__options__static__is__local": data__attributes__send__strategy__options__static__is__local,
            "data__attributes__send__strategy__options__static__send__past__recipients__immediately": data__attributes__send__strategy__options__static__send__past__recipients__immediately,
            "data__attributes__send__strategy__options__sto__date": data__attributes__send__strategy__options__sto__date,
            "data__attributes__send__strategy__options__throttled__datetime": data__attributes__send__strategy__options__throttled__datetime,
            "data__attributes__send__strategy__options__throttled__throttle__percentage": data__attributes__send__strategy__options__throttled__throttle__percentage,
            "data__attributes__tracking__options": data__attributes__tracking__options,
            "data__type": data__type,
        }
    )
    return _invoke_mcp_tool(context, provider, tool_name, payload)


def klaviyo_create_campaign_send_job(
    context: "AgentContext",
    data__id: str,
    data__type: str,
) -> ToolInvocationResult:
    """
    Trigger a Klaviyo campaign send job.
    """
    provider = "klaviyo"
    tool_name = "KLAVIYO_CREATE_CAMPAIGN_SEND_JOB"
    ensure_authorized(context, provider)
    payload = _clean_payload(
        {
            "data__id": data__id,
            "data__type": data__type,
        }
    )
    return _invoke_mcp_tool(context, provider, tool_name, payload)
