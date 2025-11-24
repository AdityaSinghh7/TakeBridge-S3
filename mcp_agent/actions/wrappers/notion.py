from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict

from mcp_agent.types import ToolInvocationResult

from ._common import _clean_payload, _invoke_mcp_tool, ensure_authorized

if TYPE_CHECKING:
    from mcp_agent.core.context import AgentContext


def notion_create_notion_page(
    context: "AgentContext",
    parent_id: str,
    title: str,
    cover: str | None = None,
    icon: str | None = None,
) -> ToolInvocationResult:
    """
    Create a new Notion page under a specified parent.

    Args:
        parent_id: Parent page or database ID.
        title: Page title.
        cover: Optional cover URL.
        icon: Optional icon URL or emoji.
    """
    provider = "notion"
    tool_name = "NOTION_CREATE_NOTION_PAGE"
    ensure_authorized(context, provider)
    payload = _clean_payload(
        {
            "parent_id": parent_id,
            "title": title,
            "cover": cover,
            "icon": icon,
        }
    )
    return _invoke_mcp_tool(context, provider, tool_name, payload)


def notion_update_page(
    context: "AgentContext",
    page_id: str,
    properties: Dict[str, Any] | None = None,
    archived: bool | None = None,
    cover: Dict[str, Any] | None = None,
    icon: Dict[str, Any] | None = None,
) -> ToolInvocationResult:
    """
    Update Notion page properties, icon, cover, or archive status.

    Args:
        page_id: Page ID to update.
        properties: Properties payload to update.
        archived: Archive flag.
        cover: Cover configuration.
        icon: Icon configuration.
    """
    provider = "notion"
    tool_name = "NOTION_UPDATE_PAGE"
    ensure_authorized(context, provider)
    payload = _clean_payload(
        {
            "page_id": page_id,
            "properties": properties,
            "archived": archived,
            "cover": cover,
            "icon": icon,
        }
    )
    return _invoke_mcp_tool(context, provider, tool_name, payload)
