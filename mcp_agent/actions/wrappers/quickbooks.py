from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List

from mcp_agent.types import ToolInvocationResult

from ._common import _clean_payload, _invoke_mcp_tool, ensure_authorized

if TYPE_CHECKING:
    from mcp_agent.core.context import AgentContext


def quickbooks_create_invoice(
    context: "AgentContext",
    customer_id: str,
    lines: List[Any],
    minorversion: int | None = None,
) -> ToolInvocationResult:
    """
    Create a new invoice in QuickBooks.
    """
    provider = "quickbooks"
    tool_name = "QUICKBOOKS_CREATE_INVOICE"
    ensure_authorized(context, provider)
    payload = _clean_payload(
        {
            "customer_id": customer_id,
            "lines": lines,
            "minorversion": minorversion,
        }
    )
    return _invoke_mcp_tool(context, provider, tool_name, payload)


def quickbooks_create_customer(
    context: "AgentContext",
    display_name: str | None = None,
    family_name: str | None = None,
    given_name: str | None = None,
    middle_name: str | None = None,
    suffix: str | None = None,
    title: str | None = None,
) -> ToolInvocationResult:
    """
    Create a new customer in QuickBooks.
    """
    provider = "quickbooks"
    tool_name = "QUICKBOOKS_CREATE_CUSTOMER"
    ensure_authorized(context, provider)
    payload = _clean_payload(
        {
            "display_name": display_name,
            "family_name": family_name,
            "given_name": given_name,
            "middle_name": middle_name,
            "suffix": suffix,
            "title": title,
        }
    )
    return _invoke_mcp_tool(context, provider, tool_name, payload)
