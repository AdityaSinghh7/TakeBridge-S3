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

stripe_create_refund.__tb_output_schema__ = {
  "properties": {
    "data": {
      "additionalProperties": True,
      "description": "The full Stripe Refund object detailing the created refund.",
      "title": "Data",
      "type": "object"
    },
    "error": {
      "default": None,
      "description": "Error if any occurred during the execution of the action",
      "nullable": True,
      "title": "Error",
      "type": "string"
    },
    "successful": {
      "description": "Whether or not the action execution was successful or not",
      "title": "Successful",
      "type": "boolean"
    }
  },
  "required": [
    "data",
    "successful"
  ],
  "title": "CreateRefundResponseWrapper",
  "type": "object"
}


def stripe_list_payment_intents(
    context: "AgentContext",
    created: Dict[str, int] | None = None,
    customer: str | None = None,
    ending_before: str | None = None,
    limit: int | None = None,
    starting_after: str | None = None,
) -> ToolInvocationResult:
    """
    List Stripe PaymentIntents with optional pagination and filters.

    Args:
        created: Filter by creation date using Unix timestamps (keys: gte, lte, gt, lt).
        customer: Customer ID to filter by.
        ending_before: Cursor for paginating backwards.
        limit: Max number of PaymentIntents to return (1-100).
        starting_after: Cursor for paginating forwards.
    """
    provider = "stripe"
    tool_name = "STRIPE_LIST_PAYMENT_INTENTS"
    ensure_authorized(context, provider)

    if limit is not None and not (1 <= limit <= 100):
        raise ValueError("Stripe list payment intents limit must be between 1 and 100.")

    payload = _clean_payload(
        {
            "created": created,
            "customer": customer,
            "ending_before": ending_before,
            "limit": limit,
            "starting_after": starting_after,
        }
    )
    return _invoke_mcp_tool(context, provider, tool_name, payload)


stripe_list_payment_intents.__tb_output_schema__ = {
  "properties": {
    "data": {
      "description": "A list of PaymentIntent objects retrieved from Stripe, conforming to the specified query parameters. Each object in the list is a dictionary representing a PaymentIntent.",
      "items": {
        "additionalProperties": True,
        "properties": {},
        "type": "object"
      },
      "title": "Data",
      "type": "array"
    },
    "error": {
      "default": None,
      "description": "Error if any occurred during the execution of the action",
      "nullable": True,
      "title": "Error",
      "type": "string"
    },
    "successful": {
      "description": "Whether or not the action execution was successful or not",
      "title": "Successful",
      "type": "boolean"
    }
  },
  "required": [
    "data",
    "successful"
  ],
  "title": "ListPaymentIntentsResponseWrapper",
  "type": "object"
}


def stripe_retrieve_refund(context: "AgentContext", refund_id: str) -> ToolInvocationResult:
    """
    Retrieve a specific Stripe refund by ID.

    Args:
        refund_id: The refund identifier (starts with \"re_\").
    """
    provider = "stripe"
    tool_name = "STRIPE_RETRIEVE_REFUND"
    ensure_authorized(context, provider)
    payload = _clean_payload({"refund_id": refund_id})
    return _invoke_mcp_tool(context, provider, tool_name, payload)


stripe_retrieve_refund.__tb_output_schema__ = {
  "properties": {
    "data": {
      "additionalProperties": False,
      "description": "Data from the action execution",
      "properties": {
        "amount": {
          "description": "The total amount of the refund, in the smallest currency unit (e.g., cents for USD, yen for JPY).",
          "title": "Amount",
          "type": "integer"
        },
        "balance_transaction": {
          "default": None,
          "description": "The ID of the Balance Transaction object that records the impact of this refund on your Stripe balance. This field is null if the refund is pending or has not yet affected the balance.",
          "nullable": True,
          "title": "Balance Transaction",
          "type": "string"
        },
        "charge": {
          "default": None,
          "description": "The ID of the Charge object that was refunded.",
          "nullable": True,
          "title": "Charge",
          "type": "string"
        },
        "created": {
          "description": "Timestamp (Unix epoch seconds) at which the refund object was created.",
          "title": "Created",
          "type": "integer"
        },
        "currency": {
          "description": "Three-letter ISO currency code (e.g., 'usd', 'eur') representing the currency of the refund, in lowercase.",
          "title": "Currency",
          "type": "string"
        },
        "destination_details": {
          "additionalProperties": False,
          "default": None,
          "description": "Represents details about the destination of a refund, such as a card or bank account.",
          "nullable": True,
          "properties": {
            "card": {
              "additionalProperties": True,
              "default": None,
              "description": "If the refund was made to a card, this object contains details about the card. This will be null if the refund destination is not a card or if details are not available.",
              "nullable": True,
              "title": "Card",
              "type": "object"
            },
            "type": {
              "default": None,
              "description": "The type of the destination where the refund was sent (e.g., 'card', 'bank_account').",
              "nullable": True,
              "title": "Type",
              "type": "string"
            }
          },
          "title": "DestinationDetails",
          "type": "object"
        },
        "id": {
          "description": "Unique identifier for the refund object. This ID starts with 're_'.",
          "title": "Id",
          "type": "string"
        },
        "metadata": {
          "additionalProperties": True,
          "description": "A set of key-value pairs that you can attach to a refund object. It can be useful for storing additional information about the refund in a structured format.",
          "title": "Metadata",
          "type": "object"
        },
        "object": {
          "description": "String representing the object's type. For refund objects, the value is always 'refund'.",
          "title": "Object",
          "type": "string"
        },
        "payment_intent": {
          "default": None,
          "description": "The ID of the PaymentIntent object that is associated with the refunded charge. This field is null if the refund is not linked to a PaymentIntent.",
          "nullable": True,
          "title": "Payment Intent",
          "type": "string"
        },
        "reason": {
          "default": None,
          "description": "The reason for the refund. Possible values are: `duplicate`, `fraudulent`, `requested_by_customer`. This field can be null if no specific reason was provided or if the refund was initiated for other reasons.",
          "nullable": True,
          "title": "Reason",
          "type": "string"
        },
        "receipt_number": {
          "default": None,
          "description": "The transaction-specific receipt number issued for this refund. This number is generated by Stripe and can be displayed to the customer. This field is null if a receipt number was not generated.",
          "nullable": True,
          "title": "Receipt Number",
          "type": "string"
        },
        "source_transfer_reversal": {
          "default": None,
          "description": "The ID of the transfer reversal if this refund is reversing a transfer (e.g., in Stripe Connect). This field is null if the refund is not related to a transfer reversal from a source.",
          "nullable": True,
          "title": "Source Transfer Reversal",
          "type": "string"
        },
        "status": {
          "description": "The current status of the refund. Possible values are: `pending`, `requires_action`, `succeeded`, `failed`, or `canceled`.",
          "title": "Status",
          "type": "string"
        },
        "transfer_reversal": {
          "default": None,
          "description": "The ID of the TransferReversal object created when this refund is processed. This is relevant for refunds that are part of a Connect transfer. This field is null if the refund is not associated with a transfer reversal.",
          "nullable": True,
          "title": "Transfer Reversal",
          "type": "string"
        }
      },
      "required": [
        "id",
        "object",
        "amount",
        "created",
        "currency",
        "status"
      ],
      "title": "Data",
      "type": "object"
    },
    "error": {
      "default": None,
      "description": "Error if any occurred during the execution of the action",
      "nullable": True,
      "title": "Error",
      "type": "string"
    },
    "successful": {
      "description": "Whether or not the action execution was successful or not",
      "title": "Successful",
      "type": "boolean"
    }
  },
  "required": [
    "data",
    "successful"
  ],
  "title": "RetrieveRefundResponseWrapper",
  "type": "object"
}


def stripe_retrieve_payment_intent(
    context: "AgentContext",
    payment_intent_id: str,
    client_secret: str | None = None,
) -> ToolInvocationResult:
    """
    Retrieve a Stripe PaymentIntent by ID.

    Args:
        payment_intent_id: The PaymentIntent identifier (starts with \"pi_\").
        client_secret: Client secret when required (publishable key usage).
    """
    provider = "stripe"
    tool_name = "STRIPE_RETRIEVE_PAYMENT_INTENT"
    ensure_authorized(context, provider)
    payload = _clean_payload({"payment_intent_id": payment_intent_id, "client_secret": client_secret})
    return _invoke_mcp_tool(context, provider, tool_name, payload)


stripe_retrieve_payment_intent.__tb_output_schema__ = {
  "properties": {
    "data": {
      "additionalProperties": False,
      "description": "Data from the action execution",
      "properties": {
        "amount": {
          "description": "The amount intended to be collected by this PaymentIntent, in the smallest currency unit (e.g., cents for USD).",
          "title": "Amount",
          "type": "integer"
        },
        "client_secret": {
          "default": None,
          "description": "The client secret of this PaymentIntent. This is used for client-side confirmation of the PaymentIntent.",
          "nullable": True,
          "title": "Client Secret",
          "type": "string"
        },
        "currency": {
          "description": "The three-letter ISO currency code (e.g., usd, eur).",
          "title": "Currency",
          "type": "string"
        },
        "customer": {
          "default": None,
          "description": "The ID of the Customer this PaymentIntent is associated with, if any.",
          "nullable": True,
          "title": "Customer",
          "type": "string"
        },
        "id": {
          "description": "Unique identifier for the PaymentIntent object.",
          "title": "Id",
          "type": "string"
        },
        "metadata": {
          "additionalProperties": True,
          "default": None,
          "description": "A set of key-value pairs that you can attach to the PaymentIntent object. It can be useful for storing additional information about the charge in a structured format.",
          "nullable": True,
          "title": "Metadata",
          "type": "object"
        },
        "payment_method": {
          "default": None,
          "description": "The ID of the payment method used or to be used in this PaymentIntent.",
          "nullable": True,
          "title": "Payment Method",
          "type": "string"
        },
        "status": {
          "description": "The current status of this PaymentIntent. Common statuses include: 'requires_payment_method', 'requires_confirmation', 'requires_action', 'processing', 'succeeded', 'canceled', and 'requires_capture'.",
          "title": "Status",
          "type": "string"
        }
      },
      "required": [
        "id",
        "amount",
        "currency",
        "status"
      ],
      "title": "Data",
      "type": "object"
    },
    "error": {
      "default": None,
      "description": "Error if any occurred during the execution of the action",
      "nullable": True,
      "title": "Error",
      "type": "string"
    },
    "successful": {
      "description": "Whether or not the action execution was successful or not",
      "title": "Successful",
      "type": "boolean"
    }
  },
  "required": [
    "data",
    "successful"
  ],
  "title": "RetrievePaymentIntentResponseWrapper",
  "type": "object"
}


def stripe_list_refunds(
    context: "AgentContext",
    charge: str | None = None,
    ending_before: str | None = None,
    limit: int | None = None,
    payment_intent: str | None = None,
    starting_after: str | None = None,
) -> ToolInvocationResult:
    """
    List Stripe refunds with optional filters and pagination.

    Args:
        charge: Filter refunds to a specific charge ID.
        ending_before: Cursor to return refunds created before this ID.
        limit: Maximum number of refunds to return (1-100).
        payment_intent: Filter refunds to a specific payment intent ID.
        starting_after: Cursor to return refunds created after this ID.
    """
    provider = "stripe"
    tool_name = "STRIPE_LIST_REFUNDS"
    ensure_authorized(context, provider)

    if limit is not None and not (1 <= limit <= 100):
        raise ValueError("Stripe list refunds limit must be between 1 and 100.")

    payload = _clean_payload(
        {
            "charge": charge,
            "ending_before": ending_before,
            "limit": limit,
            "payment_intent": payment_intent,
            "starting_after": starting_after,
        }
    )
    return _invoke_mcp_tool(context, provider, tool_name, payload)


stripe_list_refunds.__tb_output_schema__ = {
  "properties": {
    "data": {
      "description": "A list of refund objects matching the query criteria, ordered by creation date in descending order.",
      "items": {
        "description": "Detailed model representing a single refund object from Stripe.",
        "properties": {
          "amount": {
            "description": "Amount refunded, in the smallest currency unit (e.g., cents for USD, yen for JPY).",
            "title": "Amount",
            "type": "integer"
          },
          "balance_transaction": {
            "default": None,
            "description": "ID of the balance transaction reflecting this refund's impact on the account balance.",
            "nullable": True,
            "title": "Balance Transaction",
            "type": "string"
          },
          "charge": {
            "default": None,
            "description": "ID of the charge that was refunded.",
            "nullable": True,
            "title": "Charge",
            "type": "string"
          },
          "created": {
            "description": "Timestamp (in seconds since the Unix epoch) indicating when the refund object was created.",
            "title": "Created",
            "type": "integer"
          },
          "currency": {
            "description": "Three-letter ISO currency code (e.g., 'usd', 'eur') representing the currency of the refund.",
            "title": "Currency",
            "type": "string"
          },
          "id": {
            "description": "Unique identifier for the refund object. (e.g., 're_1KvLBN2eZvKYlo2Cl2u0nZLJ')",
            "title": "Id",
            "type": "string"
          },
          "metadata": {
            "additionalProperties": True,
            "description": "A set of key-value pairs that you can attach to a refund object. Useful for storing additional, structured information about the refund.",
            "title": "Metadata",
            "type": "object"
          },
          "object": {
            "description": "String representing the object's type. For refund objects, the value is 'refund'.",
            "title": "Object",
            "type": "string"
          },
          "payment_intent": {
            "default": None,
            "description": "ID of the PaymentIntent for the charge that was refunded.",
            "nullable": True,
            "title": "Payment Intent",
            "type": "string"
          },
          "reason": {
            "default": None,
            "description": "Reason for the refund (e.g., 'duplicate', 'fraudulent', 'requested_by_customer').",
            "nullable": True,
            "title": "Reason",
            "type": "string"
          },
          "receipt_number": {
            "default": None,
            "description": "Receipt number for this refund, displayable to the customer.",
            "nullable": True,
            "title": "Receipt Number",
            "type": "string"
          },
          "status": {
            "description": "The current status of the refund. Possible values: 'pending', 'succeeded', 'failed', 'canceled'. 'requires_action' may also appear for certain payment methods.",
            "title": "Status",
            "type": "string"
          },
          "transfer_reversal": {
            "default": None,
            "description": "ID of the transfer reversal if the refund is associated with a reversed transfer.",
            "nullable": True,
            "title": "Transfer Reversal",
            "type": "string"
          }
        },
        "required": [
          "id",
          "object",
          "amount",
          "created",
          "currency",
          "status"
        ],
        "title": "RefundData",
        "type": "object"
      },
      "title": "Data",
      "type": "array"
    },
    "error": {
      "default": None,
      "description": "Error if any occurred during the execution of the action",
      "nullable": True,
      "title": "Error",
      "type": "string"
    },
    "has_more": {
      "description": "A boolean flag indicating whether there are more refunds available beyond the current list. If true, use the ID of the last refund in the 'data' array as the 'starting_after' parameter in a subsequent request to fetch the next page.",
      "title": "Has More",
      "type": "boolean"
    },
    "object": {
      "description": "String representing the object's type. Always 'list' for this response.",
      "title": "Object",
      "type": "string"
    },
    "successful": {
      "description": "Whether or not the action execution was successful or not",
      "title": "Successful",
      "type": "boolean"
    },
    "url": {
      "description": "The API URL endpoint from which this list of refunds was fetched.",
      "title": "Url",
      "type": "string"
    }
  },
  "required": [
    "object",
    "url",
    "has_more",
    "data",
    "successful"
  ],
  "title": "ListRefundsResponseWrapper",
  "type": "object"
}


def stripe_retrieve_charge(context: "AgentContext", charge_id: str) -> ToolInvocationResult:
    """
    Retrieve a Stripe charge by ID.

    Args:
        charge_id: The charge identifier (starts with \"ch_\").
    """
    provider = "stripe"
    tool_name = "STRIPE_RETRIEVE_CHARGE"
    ensure_authorized(context, provider)
    payload = _clean_payload({"charge_id": charge_id})
    return _invoke_mcp_tool(context, provider, tool_name, payload)


stripe_retrieve_charge.__tb_output_schema__ = {
  "properties": {
    "data": {
      "additionalProperties": False,
      "description": "Data from the action execution",
      "properties": {
        "amount": {
          "description": "Amount in the smallest currency unit (e.g., 100 for $1.00 or ¥100).",
          "title": "Amount",
          "type": "integer"
        },
        "created": {
          "description": "Creation timestamp (Unix epoch seconds).",
          "title": "Created",
          "type": "integer"
        },
        "currency": {
          "description": "Three-letter ISO currency code, lowercase (e.g., usd, gbp, eur).",
          "title": "Currency",
          "type": "string"
        },
        "customer": {
          "default": None,
          "description": "Associated customer ID.",
          "nullable": True,
          "title": "Customer",
          "type": "string"
        },
        "description": {
          "default": None,
          "description": "Arbitrary string, often useful for user display.",
          "nullable": True,
          "title": "Description",
          "type": "string"
        },
        "id": {
          "description": "Unique charge identifier.",
          "title": "Id",
          "type": "string"
        },
        "metadata": {
          "additionalProperties": True,
          "description": "Key-value pairs for storing additional structured information.",
          "title": "Metadata",
          "type": "object"
        },
        "payment_method_details": {
          "additionalProperties": True,
          "description": "Details of the payment method used; structure varies by type (e.g., card, bank transfer).",
          "title": "Payment Method Details",
          "type": "object"
        },
        "status": {
          "description": "Charge status: `succeeded`, `pending`, or `failed`.",
          "title": "Status",
          "type": "string"
        }
      },
      "required": [
        "id",
        "amount",
        "currency",
        "status",
        "payment_method_details",
        "created"
      ],
      "title": "Data",
      "type": "object"
    },
    "error": {
      "default": None,
      "description": "Error if any occurred during the execution of the action",
      "nullable": True,
      "title": "Error",
      "type": "string"
    },
    "successful": {
      "description": "Whether or not the action execution was successful or not",
      "title": "Successful",
      "type": "boolean"
    }
  },
  "required": [
    "data",
    "successful"
  ],
  "title": "RetrieveChargeResponseWrapper",
  "type": "object"
}
