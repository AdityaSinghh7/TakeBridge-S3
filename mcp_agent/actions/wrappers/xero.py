from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List

from mcp_agent.types import ToolInvocationResult

from ._common import _clean_payload, _invoke_mcp_tool, ensure_authorized

if TYPE_CHECKING:
    from mcp_agent.core.context import AgentContext


def xero_create_invoice(
    context: "AgentContext",
    ContactID: str,
    LineItems: List[Any],
    Type: str,
    CurrencyCode: str | None = None,
    Date: str | None = None,
    DueDate: str | None = None,
    InvoiceNumber: str | None = None,
    Reference: str | None = None,
    Status: str | None = None,
    tenant_id: str | None = None,
) -> ToolInvocationResult:
    """
    Create a new invoice in Xero.
    """
    provider = "xero"
    tool_name = "XERO_CREATE_INVOICE"
    ensure_authorized(context, provider)
    payload = _clean_payload(
        {
            "ContactID": ContactID,
            "LineItems": LineItems,
            "Type": Type,
            "CurrencyCode": CurrencyCode,
            "Date": Date,
            "DueDate": DueDate,
            "InvoiceNumber": InvoiceNumber,
            "Reference": Reference,
            "Status": Status,
            "tenant_id": tenant_id,
        }
    )
    return _invoke_mcp_tool(context, provider, tool_name, payload)


def xero_create_purchase_order(
    context: "AgentContext",
    ContactID: str,
    LineItems: List[Any],
    Date: str | None = None,
    DeliveryDate: str | None = None,
    Reference: str | None = None,
    Status: str | None = None,
    tenant_id: str | None = None,
) -> ToolInvocationResult:
    """
    Create a purchase order in Xero.
    """
    provider = "xero"
    tool_name = "XERO_CREATE_PURCHASE_ORDER"
    ensure_authorized(context, provider)
    payload = _clean_payload(
        {
            "ContactID": ContactID,
            "LineItems": LineItems,
            "Date": Date,
            "DeliveryDate": DeliveryDate,
            "Reference": Reference,
            "Status": Status,
            "tenant_id": tenant_id,
        }
    )
    return _invoke_mcp_tool(context, provider, tool_name, payload)
