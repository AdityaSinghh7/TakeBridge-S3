"""High-signal key extraction for MCP tool responses.

This module centralizes:
- Mapping of provider/tool -> high-signal dotted paths
- Extraction of those paths from normalized tool results
- Emission of a lightweight event for downstream subscribers
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, Mapping

from mcp_agent.execution.response_ops import MCPResponseOps
from shared.streaming import emit_event

# Manually curated high-signal paths per provider/tool.
# Paths are dotted and operate on the unwrapped data payload.
HIGH_SIGNAL_KEYS: Dict[str, Dict[str, Iterable[str]]] = {
    "gmail": {
        # Message search: surface message IDs and snippets if present
        "GMAIL_FETCH_EMAILS": [
            "messages[*].subject",
            "messages[*].sender",
            "messages[*].messageTimestamp",
            "resultSizeEstimate",
        ],
        # Send email: surface IDs for follow-up threading
        "GMAIL_SEND_EMAIL": [
            "snippet",
            "labelIds",
            "id",
        ],
        "GMAIL_SEND_DRAFT": [
            "data.id",
            "data.snippet",
            "data.threadId",
        ],
        "GMAIL_CREATE_EMAIL_DRAFT": [
            "data.id",
            "data.message.id",
            "data.message.threadId",
            "data.message.snippet",
        ],
    },
    "slack": {
        # Post message: channel/ts plus text if returned
        "SLACK_SEND_MESSAGE": [
            "channel",
            "ts",
            "message.text",
            "ok",
        ],
    },
    "shopify": {
        # Orders query: surface key order attributes across all returned orders
        "SHOPIFY_GET_ORDERS_WITH_FILTERS": [
            "orders[*].id",
            "orders[*].name",  # Human-readable order identifier (e.g., #1001)
            "orders[*].order_number",
            "orders[*].total_price",  # Bottom line value
            "orders[*].currency",  # Currency for the price
            "orders[*].financial_status",  # Payment state
            "orders[*].fulfillment_status",  # Fulfillment state
            "orders[*].email",  # Customer email identifier
            "orders[*].created_at",  # Recency timestamp
            "orders[*].line_items[0].name",  # First line item name per order
            "orders[*].subtotal_price",
            "orders[*].total_discounts",
            "orders[*].total_tax",
            "orders[*].shipping_address.country",
            "orders[*].shipping_address.city",
        ],
        # Order list: similar signal set for paginated listings
        "SHOPIFY_GET_ORDER_LIST": [
            "orders[*].id",
            "orders[*].name",
            "orders[*].order_number",
            "orders[*].total_price",
            "orders[*].currency",
            "orders[*].financial_status",
            "orders[*].fulfillment_status",
            "orders[*].email",
            "orders[*].created_at",
            "orders[*].line_items[0].title",
        ],
        # Customer lookup: surface core customer metadata
        "SHOPIFY_GET_CUSTOMER": [
            "customer.id",
            "customer.email",
            "customer.first_name",
            "customer.last_name",
            "customer.phone",
            "customer.state",
            "customer.orders_count",
            "customer.total_spent",
            "customer.tags",
            "customer.created_at",
            "customer.updated_at",
            "customer.default_address.city",
            "customer.default_address.country",
            "customer.email_marketing_consent.state",
            "customer.sms_marketing_consent.state",
        ],
        # Order-by-ID detail view: surface the core metadata plus first line item
        "SHOPIFY_GET_ORDERSBY_ID": [
            "id",  # Unique order ID
            "name",  # Human-friendly label (e.g., #1001)
            "order_number",  # Sequential display number
            "token",  # Unique storefront token
            "currency",  # Currency code for the order
            "total_price",  # Total charged amount
            "subtotal_price",  # Amount before shipping/taxes
            "total_tax",  # Tax amount collected
            "total_discounts",  # Discounts applied
            "financial_status",  # Payment state
            "fulfillment_status",  # Fulfillment progress
            "created_at",  # Timestamp of creation
            "updated_at",  # Last update timestamp
            "contact_email",  # Customer email
            "shipping_address.city",  # Shipping destination city
            "shipping_address.country",  # Shipping destination country
            "billing_address.city",  # Billing city if available
            "source_name",  # Origin channel (web, pos, etc.)
            "tags",  # Order tags
            "line_items[0].title",  # First line item title
        ],
        "SHOPIFY_UPDATE_ORDER": [
            "id",
            "order_number",
            "name",
            "token",
            "currency",
            "total_price",
            "subtotal_price",
            "total_tax",
            "total_discounts",
            "financial_status",
            "fulfillment_status",
            "updated_at",
            "contact_email",
            "shipping_address.city",
            "shipping_address.country",
        ],
        "SHOPIFY_GRAPH_QL_QUERY": [
            "errors[*].message",
            "errors[*].extensions.code",
            "errors[*].path",
            "extensions.cost.requestedQueryCost",
            "extensions.cost.actualQueryCost",
            "extensions.cost.throttleStatus.currentlyAvailable",
            "extensions.cost.throttleStatus.maximumAvailable",
            "extensions.cost.throttleStatus.restoreRate",
        ],
    },
    "googlesheets": {
        "GOOGLESHEETS_BATCH_GET": [
            "spreadsheetId",
            "valueRanges[*].range",
            "valueRanges[*].majorDimension",
            "valueRanges[*].values",
        ],
        "GOOGLESHEETS_SPREADSHEETS_VALUES_APPEND": [
            "spreadsheetId",
            "tableRange",
            "updates.updatedRange",
            "updates.updatedRows",
            "updates.updatedCells",
        ],
        "GOOGLESHEETS_FIND_WORKSHEET_BY_TITLE": [
            "found",
        ],
        "GOOGLESHEETS_ADD_SHEET": [
            "spreadsheetId",
            "replies[*].addSheet.sheetId",
            "replies[*].addSheet.title",
        ],
    },
    "googledocs": {
        "GOOGLEDOCS_GET_DOCUMENT_BY_ID": [
            "response_data.documentId",
            "response_data.title",
            "response_data.revisionId",
        ],
        "GOOGLEDOCS_SEARCH_DOCUMENTS": [
            "documents[*].id",
            "documents[*].name",
            "documents[*].modifiedTime",
            "documents[*].createdTime",
            "documents[*].webViewLink",
            "total_found",
        ],
    },
    "googleslides": {
        "GOOGLESLIDES_CREATE_SLIDES_MARKDOWN": [
            "presentation_id",
            "slide_count",
        ],
    },
    "googledrive": {
        "GOOGLEDRIVE_UPLOAD_FILE": [
            "data.id",
            "data.name",
            "data.mimeType",
            "data.size",
            "data.webViewLink",
            "data.webContentLink",
            "data.parents",
            "data.ownedByMe",
            "data.shared",
            "data.createdTime",
            "data.modifiedTime",
            "data.capabilities.canEdit",
            "data.capabilities.canDownload",
            "data.capabilities.canShare",
        ],
    },
}


def _collect_signals(data: Any, paths: Iterable[str]) -> Dict[str, Any]:
    """Extract values for dotted paths from unwrapped data."""
    signals: Dict[str, Any] = {}
    # Reuse MCPResponseOps traversal; instantiate with already-unwrapped data
    data_ops = MCPResponseOps(data if isinstance(data, dict) else {"value": data})
    for path in paths:
        # Handle simple wildcard pattern messages[*].field
        if "[*]." in path:
            base, _, field = path.partition("[*].")
            items = data_ops.get_by_path(base, default=[])
            if isinstance(items, list):
                extracted = []
                for item in items:
                    if isinstance(item, dict) and field in item:
                        extracted.append(item[field])
                if extracted:
                    signals[path] = extracted
            continue

        value = data_ops.get_by_path(path, default=None)
        if value is not None:
            signals[path] = value
    return signals


def emit_high_signal(provider: str, tool: str, result: Mapping[str, Any]) -> None:
    """
    Emit high-signal fields for a tool invocation.

    Args:
        provider: Provider name
        tool: Tool name (MCP/composio tool identifier)
        result: Normalized ToolInvocationResult dict
    """
    ops = MCPResponseOps(dict(result))
    success = ops.is_success()

    # Emit error-only payload on failure
    if not success:
        emit_event(
            "mcp.high_signal",
            {
                "provider": provider,
                "tool": tool,
                "success": False,
                "error": ops.get_error(),
            },
        )
        return

    paths = HIGH_SIGNAL_KEYS.get(provider, {}).get(tool, [])
    if not paths:
        return

    unwrapped_data = ops.unwrap_data()
    signals = _collect_signals(unwrapped_data, paths)
    if not signals:
        return

    emit_event(
        "mcp.high_signal",
        {
            "provider": provider,
            "tool": tool,
            "success": True,
            "signals": signals,
        },
    )


__all__ = ["emit_high_signal", "HIGH_SIGNAL_KEYS"]
