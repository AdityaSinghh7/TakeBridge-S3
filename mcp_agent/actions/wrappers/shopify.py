from __future__ import annotations

from typing import TYPE_CHECKING

from mcp_agent.types import ToolInvocationResult

from ._common import _clean_payload, _invoke_mcp_tool, ensure_authorized

if TYPE_CHECKING:
    from mcp_agent.core.context import AgentContext

from ..shopify_output import (
    shopify_get_order_list_output_schema,
    shopify_get_orders_with_filters_output_schema,
    shopify_get_ordersby_id_output_schema,
    shopify_get_customer_output_schema,
    shopify_update_order_output_schema,
    shopify_graph_ql_query_output_schema,
)


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
    order_payload: dict[str, object] = {"id": id}
    if phone is not None:
        order_payload["phone"] = phone
    payload = _clean_payload(
        {
            # Shopify REST order update expects body nested under "order"
            "order": order_payload,
            # Composio request schema still requires top-level id (and optionally phone)
            "id": id,
            "phone": phone,
        }
    )
    return _invoke_mcp_tool(context, provider, tool_name, payload)


shopify_update_order.__tb_output_schema__ = shopify_update_order_output_schema


def shopify_get_ordersby_id(context: "AgentContext", order_id: str, fields: str | None = None) -> ToolInvocationResult:
    """
    Retrieve a Shopify order by ID.

    Args:
        order_id: The unique identifier of the order to retrieve.
        fields: Optional comma-separated list of fields to include (e.g., "id,line_items").
    """
    provider = "shopify"
    tool_name = "SHOPIFY_GET_ORDERSBY_ID"
    ensure_authorized(context, provider)
    payload = _clean_payload({"order_id": order_id, "fields": fields})
    return _invoke_mcp_tool(context, provider, tool_name, payload)


shopify_get_ordersby_id.__tb_output_schema__ = shopify_get_ordersby_id_output_schema


def shopify_get_customer(context: "AgentContext", customer_id: str) -> ToolInvocationResult:
    """
    Retrieve a Shopify customer by ID.

    Args:
        customer_id: The unique identifier for the customer (e.g., starts with digits).
    """
    provider = "shopify"
    tool_name = "SHOPIFY_GET_CUSTOMER"
    ensure_authorized(context, provider)
    payload = _clean_payload({"customer_id": customer_id})
    return _invoke_mcp_tool(context, provider, tool_name, payload)


shopify_get_customer.__tb_output_schema__ = shopify_get_customer_output_schema


def shopify_get_order_list(
    context: "AgentContext",
    attribution_app_id: str | None = None,
    created_at_max: str | None = None,
    created_at_min: str | None = None,
    fields: str | list[str] | None = None,
    financial_status: str | None = None,
    fulfillment_status: str | None = None,
    ids: str | list[int] | list[str] | None = None,
    limit: int | None = None,
    name: str | None = None,
    page_info: str | None = None,
    processed_at_max: str | None = None,
    processed_at_min: str | None = None,
    since_id: int | None = None,
    status: str | None = None,
    updated_at_max: str | None = None,
    updated_at_min: str | None = None,
) -> ToolInvocationResult:
    """
    Retrieve a list of Shopify orders with optional filters and pagination.

    Args:
        attribution_app_id: Filter to orders attributed to a specific app ID (use "current" for calling app).
        created_at_max: Latest creation timestamp (ISO 8601).
        created_at_min: Earliest creation timestamp (ISO 8601).
        fields: Comma-separated fields to include; lists are converted automatically.
        financial_status: Financial status filter.
        fulfillment_status: Fulfillment status filter.
        ids: Comma-separated order IDs; lists are converted automatically.
        limit: Maximum results per page (1-250).
        name: Order name filter (for example, #1001).
        page_info: Cursor for pagination; when set, only limit may accompany it.
        processed_at_max: Latest processed timestamp (ISO 8601).
        processed_at_min: Earliest processed timestamp (ISO 8601).
        since_id: Return orders with IDs greater than this ID.
        status: Order status filter.
        updated_at_max: Latest updated timestamp (ISO 8601).
        updated_at_min: Earliest updated timestamp (ISO 8601).
    """
    provider = "shopify"
    tool_name = "SHOPIFY_GET_ORDER_LIST"
    ensure_authorized(context, provider)

    if limit is not None and not (1 <= limit <= 250):
        raise ValueError("Shopify order list limit must be between 1 and 250.")

    def _is_set(value: object) -> bool:
        return value is not None and value != ""

    def _to_csv(value: object) -> object:
        if value is None:
            return None
        if isinstance(value, (list, tuple, set)):
            return ",".join(str(v) for v in value)
        return value

    if _is_set(page_info):
        disallowed_with_page = {
            "attribution_app_id": attribution_app_id,
            "created_at_max": created_at_max,
            "created_at_min": created_at_min,
            "fields": fields,
            "financial_status": financial_status,
            "fulfillment_status": fulfillment_status,
            "ids": ids,
            "name": name,
            "processed_at_max": processed_at_max,
            "processed_at_min": processed_at_min,
            "since_id": since_id,
            "status": status,
            "updated_at_max": updated_at_max,
            "updated_at_min": updated_at_min,
        }
        invalid_keys = [key for key, val in disallowed_with_page.items() if _is_set(val)]
        if invalid_keys:
            raise ValueError(
                "When page_info is provided, only limit may accompany it; "
                f"remove: {', '.join(sorted(invalid_keys))}."
            )

    payload = _clean_payload(
        {
            "attribution_app_id": attribution_app_id,
            "created_at_max": created_at_max,
            "created_at_min": created_at_min,
            "fields": _to_csv(fields),
            "financial_status": financial_status,
            "fulfillment_status": fulfillment_status,
            "ids": _to_csv(ids),
            "limit": limit,
            "name": name,
            "page_info": page_info,
            "processed_at_max": processed_at_max,
            "processed_at_min": processed_at_min,
            "since_id": since_id,
            "status": status,
            "updated_at_max": updated_at_max,
            "updated_at_min": updated_at_min,
        }
    )
    return _invoke_mcp_tool(context, provider, tool_name, payload)


shopify_get_order_list.__tb_output_schema__ = shopify_get_order_list_output_schema


def shopify_get_orders_with_filters(
    context: "AgentContext",
    attribution_app_id: str | None = None,
    created_at_max: str | None = None,
    created_at_min: str | None = None,
    fields: str | None = None,
    financial_status: str | None = None,
    fulfillment_status: str | None = None,
    ids: str | None = None,
    limit: int | None = None,
    name: str | None = None,
    page_info: str | None = None,
    processed_at_max: str | None = None,
    processed_at_min: str | None = None,
    since_id: int | None = None,
    status: str | None = None,
    updated_at_max: str | None = None,
    updated_at_min: str | None = None,
) -> ToolInvocationResult:
    """
    List Shopify orders with filter and pagination options.

    Note: Protected Customer Data fields may be redacted if the app is not approved for PCD.

    Args:
        attribution_app_id: Filter to orders attributed to a given app ID; use "current" for the calling app.
        created_at_max: Return orders created at or before this ISO 8601 timestamp.
        created_at_min: Return orders created at or after this ISO 8601 timestamp.
        fields: Comma-separated list of order fields to include.
        financial_status: Filter by financial status (authorized, pending, paid, partially_paid, refunded, voided, partially_refunded, any, unpaid).
        fulfillment_status: Filter by fulfillment status (shipped/fulfilled, partial, unshipped/null, any, unfulfilled).
        ids: Comma-separated list of numeric order IDs to retrieve.
        limit: Maximum number of orders per page (1-250).
        name: Filter by order name (e.g., #1001).
        page_info: Cursor for pagination; when provided, only limit (and fields where supported) should accompany this parameter.
        processed_at_max: Orders imported/processed at or before this ISO 8601 timestamp.
        processed_at_min: Orders imported/processed at or after this ISO 8601 timestamp.
        since_id: Restrict results to after this ID.
        status: Filter by order status (open, closed, cancelled, any).
        updated_at_max: Orders updated at or before this ISO 8601 timestamp.
        updated_at_min: Orders updated at or after this ISO 8601 timestamp.
    """
    provider = "shopify"
    tool_name = "SHOPIFY_GET_ORDERS_WITH_FILTERS"
    ensure_authorized(context, provider)

    if limit is not None and not (1 <= limit <= 250):
        raise ValueError("Shopify orders limit must be between 1 and 250.")

    def _is_set(value: object) -> bool:
        return value is not None and value != ""

    if _is_set(page_info):
        disallowed_with_page = {
            "attribution_app_id": attribution_app_id,
            "created_at_max": created_at_max,
            "created_at_min": created_at_min,
            "financial_status": financial_status,
            "fulfillment_status": fulfillment_status,
            "ids": ids,
            "name": name,
            "processed_at_max": processed_at_max,
            "processed_at_min": processed_at_min,
            "since_id": since_id,
            "status": status,
            "updated_at_max": updated_at_max,
            "updated_at_min": updated_at_min,
        }
        invalid_keys = [key for key, val in disallowed_with_page.items() if _is_set(val)]
        if invalid_keys:
            raise ValueError(
                "When page_info is provided, only limit and fields may accompany it; "
                f"remove: {', '.join(sorted(invalid_keys))}."
            )

    payload = _clean_payload(
        {
            "attribution_app_id": attribution_app_id,
            "created_at_max": created_at_max,
            "created_at_min": created_at_min,
            "fields": fields,
            "financial_status": financial_status,
            "fulfillment_status": fulfillment_status,
            "ids": ids,
            "limit": limit,
            "name": name,
            "page_info": page_info,
            "processed_at_max": processed_at_max,
            "processed_at_min": processed_at_min,
            "since_id": since_id,
            "status": status,
            "updated_at_max": updated_at_max,
            "updated_at_min": updated_at_min,
        }
    )
    return _invoke_mcp_tool(context, provider, tool_name, payload)

shopify_get_orders_with_filters.__tb_output_schema__ = shopify_get_orders_with_filters_output_schema


def shopify_graph_ql_query(
    context: "AgentContext",
    query: str,
    variables: dict | None = None,
) -> ToolInvocationResult:
    """
    Execute a GraphQL operation against the Shopify Admin API.

    Args:
        query: The GraphQL query string to execute against the Shopify Admin API.
        variables: Optional variables to supply to the query (dictionary).
    """
    provider = "shopify"
    tool_name = "SHOPIFY_GRAPH_QL_QUERY"
    ensure_authorized(context, provider)
    payload = _clean_payload({"query": query, "variables": variables})
    return _invoke_mcp_tool(context, provider, tool_name, payload)


shopify_graph_ql_query.__tb_output_schema__ = shopify_graph_ql_query_output_schema
