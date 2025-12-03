from __future__ import annotations

from typing import TYPE_CHECKING, Any

from mcp_agent.types import ToolInvocationResult

from ._common import _clean_payload, _invoke_mcp_tool, ensure_authorized

if TYPE_CHECKING:
    from mcp_agent.core.context import AgentContext


def dropbox_upload_file(
    context: "AgentContext",
    path: str,
    content: Any,
    autorename: bool | None = None,
    mode: str = "add",
    mute: bool | None = None,
    strict_conflict: bool | None = None,
) -> ToolInvocationResult:
    """
    Upload a file to Dropbox at a specified path.

    Args:
        path: Destination path in Dropbox.
        content: File content payload.
        autorename: Whether to autorename on conflict.
        mode: Upload mode (default add).
        mute: Whether to mute notifications.
        strict_conflict: Whether to enforce strict conflict handling.
    """
    provider = "dropbox"
    tool_name = "DROPBOX_UPLOAD_FILE"
    ensure_authorized(context, provider)
    payload = _clean_payload(
        {
            "path": path,
            "content": content,
            "autorename": autorename,
            "mode": mode,
            "mute": mute,
            "strict_conflict": strict_conflict,
        }
    )
    return _invoke_mcp_tool(context, provider, tool_name, payload)


dropbox_upload_file.__tb_output_schema__ = {
  "properties": {
    "data": {
      "additionalProperties": False,
      "description": "Data from the action execution",
      "properties": {
        "client_modified": {
          "description": "Timestamp of the last modification on the client.",
          "format": "date-time",
          "title": "Client Modified",
          "type": "string"
        },
        "content_hash": {
          "description": "A hash of the file content.",
          "title": "Content Hash",
          "type": "string"
        },
        "file_lock_info": {
          "additionalProperties": False,
          "default": None,
          "description": "Information about file locking.",
          "nullable": True,
          "properties": {
            "created": {
              "default": None,
              "description": "The time the lock was created.",
              "format": "date-time",
              "nullable": True,
              "title": "Created",
              "type": "string"
            },
            "is_lockholder": {
              "default": None,
              "description": "True if the current user is the lockholder.",
              "nullable": True,
              "title": "Is Lockholder",
              "type": "boolean"
            },
            "lockholder_name": {
              "default": None,
              "description": "The display name of the lockholder.",
              "nullable": True,
              "title": "Lockholder Name",
              "type": "string"
            }
          },
          "title": "FileLockInfo",
          "type": "object"
        },
        "has_explicit_shared_members": {
          "default": None,
          "description": "Indicates if the file has explicit shared members.",
          "nullable": True,
          "title": "Has Explicit Shared Members",
          "type": "boolean"
        },
        "id": {
          "description": "Unique identifier for the file.",
          "title": "Id",
          "type": "string"
        },
        "is_downloadable": {
          "description": "Indicates if the file can be downloaded.",
          "title": "Is Downloadable",
          "type": "boolean"
        },
        "name": {
          "description": "Name of the uploaded file.",
          "title": "Name",
          "type": "string"
        },
        "path_display": {
          "description": "Display path of the file.",
          "title": "Path Display",
          "type": "string"
        },
        "path_lower": {
          "description": "Lowercase path of the file.",
          "title": "Path Lower",
          "type": "string"
        },
        "property_groups": {
        "default": None,
          "description": "List of custom properties associated with the file.",
          "items": {
            "properties": {
              "fields": {
                "description": "A list of property field key-value pairs.",
                "items": {
                  "additionalProperties": True,
                  "properties": {},
                  "type": "object"
                },
                "title": "Fields",
                "type": "array"
              },
              "template_id": {
                "description": "A unique identifier for a property template.",
                "title": "Template Id",
                "type": "string"
              }
            },
            "required": [
              "template_id",
              "fields"
            ],
            "title": "PropertyGroup",
            "type": "object"
          },
          "nullable": True,
          "title": "Property Groups",
          "type": "array"
        },
        "rev": {
          "description": "Revision identifier of the file.",
          "title": "Rev",
          "type": "string"
        },
        "server_modified": {
          "description": "Timestamp of the last modification on the server.",
          "format": "date-time",
          "title": "Server Modified",
          "type": "string"
        },
        "sharing_info": {
          "additionalProperties": False,
          "default": None,
          "description": "Information about file sharing.",
          "nullable": True,
          "properties": {
            "modified_by": {
              "default": None,
              "description": "The display name of the user who last modified the file's sharing settings.",
              "nullable": True,
              "title": "Modified By",
              "type": "string"
            },
            "parent_shared_folder_id": {
              "default": None,
              "description": "The ID of the parent shared folder.",
              "nullable": True,
              "title": "Parent Shared Folder Id",
              "type": "string"
            },
            "read_only": {
              "default": None,
              "description": "If true, the file is read-only.",
              "nullable": True,
              "title": "Read Only",
              "type": "boolean"
            }
          },
          "title": "SharingInfo",
          "type": "object"
        },
        "size": {
          "description": "Size of the file in bytes.",
          "title": "Size",
          "type": "integer"
        }
      },
      "required": [
        "name",
        "id",
        "client_modified",
        "server_modified",
        "rev",
        "size",
        "path_lower",
        "path_display",
        "is_downloadable",
        "content_hash"
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
  "title": "DropboxUploadFileResponseWrapper",
  "type": "object"
}
