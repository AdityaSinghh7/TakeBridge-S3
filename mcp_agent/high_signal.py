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
            "orders[*].name",  # Human-readable order identifier (e.g., #1001)
            "orders[*].total_price",  # Bottom line value
            "orders[*].currency",  # Currency for the price
            "orders[*].financial_status",  # Payment state
            "orders[*].fulfillment_status",  # Fulfillment state
            "orders[*].email",  # Customer email identifier
            "orders[*].created_at",  # Recency timestamp
            "orders[*].line_items[0].name",  # First line item name per order
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
