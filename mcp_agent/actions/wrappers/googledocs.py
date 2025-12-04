from __future__ import annotations

from typing import TYPE_CHECKING

from mcp_agent.types import ToolInvocationResult

from ._common import _clean_payload, _invoke_mcp_tool, ensure_authorized

if TYPE_CHECKING:
    from mcp_agent.core.context import AgentContext


def googledocs_get_document_by_id(context: "AgentContext", doc_id: str) -> ToolInvocationResult:
    """
    Retrieve an existing Google Doc by its ID.

    Args:
        doc_id: The document identifier to fetch (no creation if missing).
    """
    provider = "googledocs"
    tool_name = "GOOGLEDOCS_GET_DOCUMENT_BY_ID"
    ensure_authorized(context, provider)
    payload = _clean_payload({"id": doc_id})
    return _invoke_mcp_tool(context, provider, tool_name, payload)


googledocs_get_document_by_id.__tb_output_schema__ = {
  "properties": {
    "data": {
      "additionalProperties": False,
      "description": "Data from the action execution",
      "properties": {
        "response_data": {
          "additionalProperties": True,
          "default": None,
          "description": "A dictionary containing the full Google Document resource, including its content, properties, and metadata.",
          "nullable": True,
          "title": "Response Data",
          "type": "object"
        }
      },
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
  "title": "FindOrCreateDocumentResponseWrapper",
  "type": "object"
}


def googledocs_search_documents(
    context: "AgentContext",
    created_after: str | None = None,
    include_trashed: bool | None = False,
    max_results: int | None = 10,
    modified_after: str | None = None,
    order_by: str | None = "modifiedTime desc",
    query: str | None = None,
    shared_with_me: bool | None = False,
    starred_only: bool | None = False,
) -> ToolInvocationResult:
    """
    Search Google Docs with filters such as creation/modification time, sharing, and starred state.

    Args:
        created_after: Return documents created after this RFC 3339 timestamp.
        include_trashed: Whether to include trashed documents.
        max_results: Maximum number of documents to return (1-1000).
        modified_after: Return documents modified after this RFC 3339 timestamp.
        order_by: Field to order results by (e.g., 'modifiedTime desc').
        query: Search query to filter documents by name or content.
        shared_with_me: Whether to return only documents shared with the current user.
        starred_only: Whether to return only starred documents.
    """
    provider = "googledocs"
    tool_name = "GOOGLEDOCS_SEARCH_DOCUMENTS"
    ensure_authorized(context, provider)

    if max_results is not None and not (1 <= max_results <= 1000):
        raise ValueError("max_results must be between 1 and 1000.")

    payload = _clean_payload(
        {
            "created_after": created_after,
            "include_trashed": include_trashed,
            "max_results": max_results,
            "modified_after": modified_after,
            "order_by": order_by,
            "query": query,
            "shared_with_me": shared_with_me,
            "starred_only": starred_only,
        }
    )
    return _invoke_mcp_tool(context, provider, tool_name, payload)


googledocs_search_documents.__tb_output_schema__ = {
  "properties": {
    "data": {
      "additionalProperties": False,
      "description": "Data from the action execution",
      "properties": {
        "documents": {
          "description": "List of Google Documents matching the search criteria. Each document contains id, name, modifiedTime, createdTime, webViewLink, and other metadata.",
          "items": {
            "additionalProperties": True,
            "properties": {},
            "type": "object"
          },
          "title": "Documents",
          "type": "array"
        },
        "next_page_token": {
          "default": None,
          "description": "Token to retrieve the next page of results, if more results are available.",
          "nullable": True,
          "title": "Next Page Token",
          "type": "string"
        },
        "total_found": {
          "description": "Total number of documents found matching the search criteria.",
          "title": "Total Found",
          "type": "integer"
        }
      },
      "required": [
        "documents",
        "total_found"
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
  "title": "SearchDocumentsResponseWrapper",
  "type": "object"
}
