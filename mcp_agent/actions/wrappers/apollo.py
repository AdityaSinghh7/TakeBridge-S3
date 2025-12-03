from __future__ import annotations

from typing import TYPE_CHECKING

from mcp_agent.types import ToolInvocationResult

from ._common import _clean_payload, _invoke_mcp_tool, ensure_authorized

if TYPE_CHECKING:
    from mcp_agent.core.context import AgentContext


def apollo_people_enrichment(
    context: "AgentContext",
    domain: str | None = None,
    email: str | None = None,
    first_name: str | None = None,
    hashed_email: str | None = None,
    id: str | None = None,
    last_name: str | None = None,
    linkedin_url: str | None = None,
    name: str | None = None,
    organization_name: str | None = None,
    reveal_personal_emails: bool | None = None,
    reveal_phone_number: bool | None = None,
    webhook_url: str | None = None,
) -> ToolInvocationResult:
    """
    Enrich and retrieve person information from Apollo.io.

    Args:
        domain: Organization domain.
        email: Person email.
        first_name: First name.
        hashed_email: Hashed email.
        id: Apollo person ID.
        last_name: Last name.
        linkedin_url: LinkedIn profile URL.
        name: Full name.
        organization_name: Organization name.
        reveal_personal_emails: Whether to reveal personal emails.
        reveal_phone_number: Whether to reveal phone numbers.
        webhook_url: Webhook URL (required if reveal_phone_number is true).
    """
    provider = "apollo"
    tool_name = "APOLLO_PEOPLE_ENRICHMENT"
    ensure_authorized(context, provider)
    payload = _clean_payload(
        {
            "domain": domain,
            "email": email,
            "first_name": first_name,
            "hashed_email": hashed_email,
            "id": id,
            "last_name": last_name,
            "linkedin_url": linkedin_url,
            "name": name,
            "organization_name": organization_name,
            "reveal_personal_emails": reveal_personal_emails,
            "reveal_phone_number": reveal_phone_number,
            "webhook_url": webhook_url,
        }
    )
    return _invoke_mcp_tool(context, provider, tool_name, payload)


apollo_people_enrichment.__tb_output_schema__ = {
  "properties": {
    "data": {
      "additionalProperties": True,
      "description": "Dictionary with enriched data for the person from Apollo.io; structure and content vary based on information found and requested.",
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
  "title": "PeopleEnrichmentResponseWrapper",
  "type": "object"
}