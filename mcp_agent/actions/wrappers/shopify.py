from __future__ import annotations

from typing import TYPE_CHECKING

from mcp_agent.types import ToolInvocationResult

from ._common import _clean_payload, _invoke_mcp_tool, ensure_authorized

if TYPE_CHECKING:
    from mcp_agent.core.context import AgentContext


def shopify_update_order(context: "AgentContext", id: int, phone: str | None = None) -> ToolInvocationResult:
    """
    Update the phone number for an existing Shopify order by ID.

    Args:
        id: Shopify order ID.
        phone: Phone number to set; pass None to remove the current phone number.
    """
    provider = "shopify"
    tool_name = "SHOPIFY_UPDATE_ORDER"
    ensure_authorized(context, provider)
    payload = _clean_payload(
        {
            "id": id,
            "phone": phone,
        }
    )
    return _invoke_mcp_tool(context, provider, tool_name, payload)
