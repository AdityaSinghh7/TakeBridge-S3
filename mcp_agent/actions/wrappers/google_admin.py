from __future__ import annotations

from typing import TYPE_CHECKING

from mcp_agent.types import ToolInvocationResult

from ._common import _clean_payload, _invoke_mcp_tool, ensure_authorized

if TYPE_CHECKING:
    from mcp_agent.core.context import AgentContext


def google_admin_create_user(
    context: "AgentContext",
    primary_email: str,
    password: str,
    given_name: str,
    family_name: str,
    change_password_at_next_login: bool = True,
    org_unit_path: str = "/",
    recovery_email: str | None = None,
    recovery_phone: str | None = None,
    suspended: bool | None = None,
) -> ToolInvocationResult:
    """
    Create a new Google Workspace user.

    Args:
        primary_email: Primary email for the user.
        password: Account password.
        given_name: Given name.
        family_name: Family name.
        change_password_at_next_login: Force password change at next login.
        org_unit_path: Organizational unit path (default "/").
        recovery_email: Optional recovery email.
        recovery_phone: Optional recovery phone.
        suspended: Whether the user is suspended.
    """
    provider = "google_admin"
    tool_name = "GOOGLE_ADMIN_CREATE_USER"
    ensure_authorized(context, provider)
    payload = _clean_payload(
        {
            "primary_email": primary_email,
            "password": password,
            "given_name": given_name,
            "family_name": family_name,
            "change_password_at_next_login": change_password_at_next_login,
            "org_unit_path": org_unit_path,
            "recovery_email": recovery_email,
            "recovery_phone": recovery_phone,
            "suspended": suspended,
        }
    )
    return _invoke_mcp_tool(context, provider, tool_name, payload)

google_admin_create_user.__tb_output_schema__ = {
  "properties": {
    "data": {
      "additionalProperties": False,
      "description": "Data from the action execution",
      "properties": {
        "response_data": {
          "additionalProperties": True,
          "description": "Full API response from Google Admin for the created user",
          "title": "Response Data",
          "type": "object"
        }
      },
      "required": [
        "response_data"
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
  "title": "CreateUserResponseWrapper",
  "type": "object"
}