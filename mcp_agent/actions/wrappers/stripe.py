from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict

from mcp_agent.types import ToolInvocationResult

from ._common import _clean_payload, _invoke_mcp_tool, ensure_authorized

if TYPE_CHECKING:
    from mcp_agent.core.context import AgentContext


def stripe_create_refund(
    context: "AgentContext",
    amount: int | None = None,
    charge: str | None = None,
    metadata: Dict[str, Any] | None = None,
    payment_intent: str | None = None,
    reason: str | None = None,
    refund_application_fee: bool | None = None,
    reverse_transfer: bool | None = None,
) -> ToolInvocationResult:
    """
    Create a full or partial refund in Stripe for a charge or payment intent.

    Args:
        amount: Optional refund amount in cents.
        charge: Charge ID to refund.
        metadata: Optional metadata object.
        payment_intent: Payment intent ID to refund.
        reason: Optional refund reason.
        refund_application_fee: Whether to refund the application fee.
        reverse_transfer: Whether to reverse the transfer.
    """
    provider = "stripe"
    tool_name = "STRIPE_CREATE_REFUND"
    ensure_authorized(context, provider)
    payload = _clean_payload(
        {
            "amount": amount,
            "charge": charge,
            "metadata": metadata,
            "payment_intent": payment_intent,
            "reason": reason,
            "refund_application_fee": refund_application_fee,
            "reverse_transfer": reverse_transfer,
        }
    )
    return _invoke_mcp_tool(context, provider, tool_name, payload)
