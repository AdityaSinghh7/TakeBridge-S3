from __future__ import annotations

from typing import TYPE_CHECKING

from mcp_agent.types import ToolInvocationResult

from ._common import _clean_payload, _invoke_mcp_tool, ensure_authorized

if TYPE_CHECKING:
    from mcp_agent.core.context import AgentContext


def googleslides_create_slides_markdown(
    context: "AgentContext",
    markdown_text: str,
    title: str,
) -> ToolInvocationResult:
    """
    Create a Google Slides presentation from Markdown text.

    Args:
        markdown_text: Markdown content to convert.
        title: Presentation title.
    """
    provider = "googleslides"
    tool_name = "GOOGLESLIDES_CREATE_SLIDES_MARKDOWN"
    ensure_authorized(context, provider)
    payload = _clean_payload(
        {
            "markdown_text": markdown_text,
            "title": title,
        }
    )
    return _invoke_mcp_tool(context, provider, tool_name, payload)
