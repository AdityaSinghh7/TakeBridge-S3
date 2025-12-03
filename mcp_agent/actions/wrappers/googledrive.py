from __future__ import annotations

from typing import TYPE_CHECKING, Any

from mcp_agent.types import ToolInvocationResult

from ._common import _clean_payload, _invoke_mcp_tool, ensure_authorized

if TYPE_CHECKING:
    from mcp_agent.core.context import AgentContext


def googledrive_upload_file(
    context: "AgentContext",
    file_to_upload: Any,
    folder_to_upload_to: str | None = None,
) -> ToolInvocationResult:
    """
    Upload a file to Google Drive, optionally into a specific folder.

    Args:
        file_to_upload: File payload (max 5MB).
        folder_to_upload_to: Folder ID to upload into; uploads to root if omitted.
    """
    provider = "googledrive"
    tool_name = "GOOGLEDRIVE_UPLOAD_FILE"
    ensure_authorized(context, provider)
    payload = _clean_payload(
        {
            "file_to_upload": file_to_upload,
            "folder_to_upload_to": folder_to_upload_to,
        }
    )
    return _invoke_mcp_tool(context, provider, tool_name, payload)


googledrive_upload_file.__tb_output_schema__ = {
  "properties": {
    "data": {
      "additionalProperties": False,
      "description": "Data from the action execution",
      "properties": {
        "appProperties": {
          "additionalProperties": {
            "type": "string"
          },
          "default": None,
          "description": "A collection of arbitrary key-value pairs which are private to the requesting app.",
          "nullable": True,
          "title": "App Properties",
          "type": "object"
        },
        "capabilities": {
          "additionalProperties": False,
          "default": None,
          "description": "Capabilities the current user has on this file.",
          "nullable": True,
          "properties": {
            "canAcceptOwnership": {
              "default": None,
              "description": "Whether the current user can accept ownership of the file.",
              "nullable": True,
              "title": "Can Accept Ownership",
              "type": "boolean"
            },
            "canAddChildren": {
              "default": None,
              "description": "Whether the current user can add children to this folder. False for non-folder items.",
              "nullable": True,
              "title": "Can Add Children",
              "type": "boolean"
            },
            "canAddFolderFromAnotherDrive": {
              "default": None,
              "description": "Whether the current user can add a folder from another drive to this folder.",
              "nullable": True,
              "title": "Can Add Folder From Another Drive",
              "type": "boolean"
            },
            "canAddMyDriveParent": {
            "default": None,
              "description": "Whether the current user can add a parent for the item in My Drive without removing an existing parent.",
              "nullable": True,
              "title": "Can Add My Drive Parent",
              "type": "boolean"
            },
            "canChangeCopyRequiresWriterPermission": {
              "default": None,
              "description": "Whether the current user can change the copyRequiresWriterPermission flag.",
              "nullable": True,
              "title": "Can Change Copy Requires Writer Permission",
              "type": "boolean"
            },
            "canChangeViewersCanCopyContent": {
              "default": None,
              "description": "Whether the current user can change the viewersCanCopyContent restriction on the file.",
              "nullable": True,
              "title": "Can Change Viewers Can Copy Content",
              "type": "boolean"
            },
            "canComment": {
              "default": None,
              "description": "Whether the current user can comment on the file.",
              "nullable": True,
              "title": "Can Comment",
              "type": "boolean"
            },
            "canCopy": {
              "default": None,
              "description": "Whether the current user can copy the file.",
              "nullable": True,
              "title": "Can Copy",
              "type": "boolean"
            },
            "canDelete": {
              "default": None,
              "description": "Whether the current user can delete the file.",
              "nullable": True,
              "title": "Can Delete",
              "type": "boolean"
            },
            "canDeleteChildren": {
              "default": None,
              "description": "Whether the current user can delete children of this folder. False for non-folder items.",
              "nullable": True,
              "title": "Can Delete Children",
              "type": "boolean"
            },
            "canDownload": {
              "default": None,
              "description": "Whether the current user can download the file.",
              "nullable": True,
              "title": "Can Download",
              "type": "boolean"
            },
            "canEdit": {
              "default": None,
              "description": "Whether the current user can edit the file's metadata or content.",
              "nullable": True,
              "title": "Can Edit",
              "type": "boolean"
            },
            "canListChildren": {
              "default": None,
              "description": "Whether the current user can list the children of this folder. False for non-folder items.",
              "nullable": True,
              "title": "Can List Children",
              "type": "boolean"
            },
            "canModifyContent": {
              "default": None,
              "description": "Whether the current user can modify the content of the file.",
              "nullable": True,
              "title": "Can Modify Content",
              "type": "boolean"
            },
            "canMoveChildrenOutOfDrive": {
              "default": None,
              "description": "Whether the current user can move children out of this drive (shared drive). Folder-specific.",
              "nullable": True,
              "title": "Can Move Children Out Of Drive",
              "type": "boolean"
            },
            "canMoveChildrenWithinDrive": {
              "default": None,
              "description": "Whether the current user can move children within this drive. Folder-specific.",
              "nullable": True,
              "title": "Can Move Children Within Drive",
              "type": "boolean"
            },
            "canMoveItemIntoDrive": {
              "default": None,
              "description": "Whether the current user can move the item into a shared drive by changing its parent.",
              "nullable": True,
              "title": "Can Move Item Into Drive",
              "type": "boolean"
            },
            "canMoveItemOutOfDrive": {
              "default": None,
              "description": "Whether the current user can move the item out of its current drive by changing its parent.",
              "nullable": True,
              "title": "Can Move Item Out Of Drive",
              "type": "boolean"
            },
            "canMoveItemWithinDrive": {
              "default": None,
              "description": "Whether the current user can move the item within the same drive by changing its parent.",
              "nullable": True,
              "title": "Can Move Item Within Drive",
              "type": "boolean"
            },
            "canReadRevisions": {
              "default": None,
              "description": "Whether the current user can read the file's revisions.",
              "nullable": True,
              "title": "Can Read Revisions",
              "type": "boolean"
            },
            "canRemoveChildren": {
              "default": None,
              "description": "Whether the current user can remove children from this folder. False for non-folder items.",
              "nullable": True,
              "title": "Can Remove Children",
              "type": "boolean"
            },
            "canRemoveMyDriveParent": {
              "default": None,
              "description": "Whether the current user can remove a My Drive parent from the item without adding another parent.",
              "nullable": True,
              "title": "Can Remove My Drive Parent",
              "type": "boolean"
            },
            "canRename": {
              "default": None,
              "description": "Whether the current user can rename the file.",
              "nullable": True,
              "title": "Can Rename",
              "type": "boolean"
            },
            "canShare": {
              "default": None,
              "description": "Whether the current user can share the file.",
              "nullable": True,
              "title": "Can Share",
              "type": "boolean"
            },
            "canTrash": {
              "default": None,
              "description": "Whether the current user can move the file to trash.",
              "nullable": True,
              "title": "Can Trash",
              "type": "boolean"
            },
            "canUntrash": {
              "default": None,
              "description": "Whether the current user can restore the file from trash.",
              "nullable": True,
              "title": "Can Untrash",
              "type": "boolean"
            },
            "canUpload": {
              "default": None,
              "description": "Whether the current user can upload content to this file or folder (e.g., update).",
              "nullable": True,
              "title": "Can Upload",
              "type": "boolean"
            },
            "canUseAdminFeatures": {
              "default": None,
              "description": "Whether the current user can use special admin features on this file (in shared drives).",
              "nullable": True,
              "title": "Can Use Admin Features",
              "type": "boolean"
            }
          },
          "title": "Capabilities",
          "type": "object"
        },
        "contentHints": {
          "additionalProperties": False,
          "default": None,
          "description": "Additional information about the content of the file. This is only available for files with binary content in Google Drive.",
          "nullable": True,
          "properties": {
            "indexableText": {
              "default": None,
              "description": "Text to be indexed for the file to improve searchability.",
              "nullable": True,
              "title": "Indexable Text",
              "type": "string"
            },
            "thumbnail": {
              "additionalProperties": False,
              "default": None,
              "description": "A thumbnail for the file.",
              "nullable": True,
              "properties": {
                "image": {
                  "default": None,
                  "description": "The URL-safe Base64 encoded image data.",
                  "nullable": True,
                  "title": "Image",
                  "type": "string"
                },
                "mimeType": {
                  "default": None,
                  "description": "The MIME type of the thumbnail.",
                  "nullable": True,
                  "title": "Mime Type",
                  "type": "string"
                }
              },
              "title": "Thumbnail",
              "type": "object"
            }
          },
          "title": "ContentHints",
          "type": "object"
        },
        "contentRestrictions": {
          "default": None,
          "description": "Content restrictions for this file.",
          "items": {
            "properties": {
              "readOnly": {
                "default": None,
                "description": "Whether the content of the file is read-only.",
                "nullable": True,
                "title": "Read Only",
                "type": "boolean"
              },
              "reason": {
                "default": None,
                "description": "Reason for why the content is restricted.",
                "nullable": True,
                "title": "Reason",
                "type": "string"
              },
              "restrictingUser": {
                "additionalProperties": False,
                "default": None,
                "description": "The user who set the restriction.",
                "nullable": True,
                "properties": {
                  "displayName": {
                    "default": None,
                    "description": "The user's display name.",
                    "nullable": True,
                    "title": "Display Name",
                    "type": "string"
                  },
                  "emailAddress": {
                    "default": None,
                    "description": "The user's email address.",
                    "nullable": True,
                    "title": "Email Address",
                    "type": "string"
                  },
                  "kind": {
                    "default": None,
                    "description": "Resource type. Always 'drive#user'.",
                    "nullable": True,
                    "title": "Kind",
                    "type": "string"
                  },
                  "me": {
                    "default": None,
                    "description": "Whether this user is the authenticated user.",
                    "nullable": True,
                    "title": "Me",
                    "type": "boolean"
                  },
                  "photoLink": {
                    "default": None,
                    "description": "A link to the user's profile photo.",
                    "nullable": True,
                    "title": "Photo Link",
                    "type": "string"
                  }
                },
                "title": "User",
                "type": "object"
              },
              "restrictionTime": {
                "default": None,
                "description": "The time at which the restriction was set (RFC 3339).",
                "nullable": True,
                "title": "Restriction Time",
                "type": "string"
              },
              "type": {
                "default": None,
                "description": "The type of restriction (e.g., 'content', 'copyRequiresWriterPermission').",
                "nullable": True,
                "title": "Type",
                "type": "string"
              }
            },
            "title": "ContentRestriction",
            "type": "object"
          },
          "nullable": True,
          "title": "Content Restrictions",
          "type": "array"
        },
        "copyRequiresWriterPermission": {
          "default": None,
          "description": "Whether to require the user to be a writer on the item in order to copy content.",
          "nullable": True,
          "title": "Copy Requires Writer Permission",
          "type": "boolean"
        },
        "createdTime": {
          "default": None,
          "description": "The time at which the file was created (RFC 3339 date-time).",
          "nullable": True,
          "title": "Created Time",
          "type": "string"
        },
        "description": {
          "default": None,
          "description": "A short description of the file.",
          "nullable": True,
          "title": "Description",
          "type": "string"
        },
        "driveId": {
          "default": None,
          "description": "The ID of the shared drive the file resides in. Only populated for items in shared drives.",
          "nullable": True,
          "title": "Drive Id",
          "type": "string"
        },
        "explicitlyTrashed": {
          "default": None,
          "description": "Whether the file has been explicitly trashed, as opposed to recursively trashed from a parent folder.",
          "nullable": True,
          "title": "Explicitly Trashed",
          "type": "boolean"
        },
        "exportLinks": {
          "additionalProperties": {
            "type": "string"
          },
          "default": None,
          "description": "Links for exporting Google Workspace documents to various MIME types. Only present for Google Workspace documents.",
          "nullable": True,
          "title": "Export Links",
          "type": "object"
        },
        "fileExtension": {
          "default": None,
          "description": "The final component of fullFileExtension. This is only available for files with binary content in Google Drive.",
          "nullable": True,
          "title": "File Extension",
          "type": "string"
        },
        "folderColorRgb": {
          "default": None,
          "description": "The color for a folder as an RGB hex string. E.g. #4f8df3",
          "nullable": True,
          "title": "Folder Color Rgb",
          "type": "string"
        },
        "fullFileExtension": {
          "default": None,
          "description": "The full file extension extracted from the name field. May contain multiple concatenated extensions, such as 'tar.gz'.",
          "nullable": True,
          "title": "Full File Extension",
          "type": "string"
        },
        "hasAugmentedPermissions": {
          "default": None,
          "nullable": True,
          "title": "Has Augmented Permissions",
          "type": "boolean"
        },
        "hasThumbnail": {
          "default": None,
          "description": "Whether this file has a thumbnail.",
          "nullable": True,
          "title": "Has Thumbnail",
          "type": "boolean"
        },
        "headRevisionId": {
          "default": None,
          "description": "The ID of the head revision of the file.",
          "nullable": True,
          "title": "Head Revision Id",
          "type": "string"
        },
        "iconLink": {
          "default": None,
          "description": "A static, unauthenticated link to the file's icon.",
          "nullable": True,
          "title": "Icon Link",
          "type": "string"
        },
        "id": {
          "description": "The ID of the file.",
          "title": "Id",
          "type": "string"
        },
        "imageMediaMetadata": {
          "additionalProperties": False,
          "default": None,
          "description": "Additional metadata about image media, if available.",
          "nullable": True,
          "properties": {
            "aperture": {
              "default": None,
              "description": "The aperture used to create the image.",
              "nullable": True,
              "title": "Aperture",
              "type": "number"
            },
            "cameraMake": {
              "default": None,
              "description": "The make of the camera used to create the image.",
              "nullable": True,
              "title": "Camera Make",
              "type": "string"
            },
            "cameraModel": {
              "default": None,
              "description": "The model of the camera used to create the image.",
              "nullable": True,
              "title": "Camera Model",
              "type": "string"
            },
            "city": {
              "default": None,
              "description": "The city in which the photo was taken.",
              "nullable": True,
              "title": "City",
              "type": "string"
            },
            "colorSpace": {
              "default": None,
              "description": "The color space of the image.",
              "nullable": True,
              "title": "Color Space",
              "type": "string"
            },
            "country": {
              "default": None,
              "description": "The country in which the photo was taken.",
              "nullable": True,
              "title": "Country",
              "type": "string"
            },
            "exposureBias": {
              "default": None,
              "description": "The exposure bias of the image.",
              "nullable": True,
              "title": "Exposure Bias",
              "type": "number"
            },
            "exposureMode": {
              "default": None,
              "description": "The exposure mode used to create the image.",
              "nullable": True,
              "title": "Exposure Mode",
              "type": "string"
            },
            "exposureTime": {
              "default": None,
              "description": "The exposure time used to create the image.",
              "nullable": True,
              "title": "Exposure Time",
              "type": "number"
            },
            "flashUsed": {
              "default": None,
              "description": "Whether a flash was used to create the image.",
              "nullable": True,
              "title": "Flash Used",
              "type": "boolean"
            },
            "focalLength": {
              "default": None,
              "description": "The focal length used to create the image.",
              "nullable": True,
              "title": "Focal Length",
              "type": "number"
            },
            "gpsProcessingMethod": {
              "default": None,
              "description": "The GPS processing method used.",
              "nullable": True,
              "title": "Gps Processing Method",
              "type": "string"
            },
            "height": {
              "default": None,
              "description": "The height of the image in pixels.",
              "nullable": True,
              "title": "Height",
              "type": "integer"
            },
            "isoSpeed": {
              "default": None,
              "description": "The ISO speed used to create the image.",
              "nullable": True,
              "title": "Iso Speed",
              "type": "integer"
            },
            "lens": {
              "default": None,
              "description": "The lens used to create the image.",
              "nullable": True,
              "title": "Lens",
              "type": "string"
            },
            "location": {
              "additionalProperties": False,
              "default": None,
              "description": "Geographic location information for the image.",
              "nullable": True,
              "properties": {
                "altitude": {
                  "default": None,
                  "description": "The altitude of the location.",
                  "nullable": True,
                  "title": "Altitude",
                  "type": "number"
                },
                "latitude": {
                  "default": None,
                  "description": "The latitude of the location.",
                  "nullable": True,
                  "title": "Latitude",
                  "type": "number"
                },
                "longitude": {
                  "default": None,
                  "description": "The longitude of the location.",
                  "nullable": True,
                  "title": "Longitude",
                  "type": "number"
                }
              },
              "title": "Location",
              "type": "object"
            },
            "maxApertureValue": {
              "default": None,
              "description": "The maximum aperture value of the image.",
              "nullable": True,
              "title": "Max Aperture Value",
              "type": "number"
            },
            "meteringMode": {
              "default": None,
              "description": "The metering mode used to create the image.",
              "nullable": True,
              "title": "Metering Mode",
              "type": "string"
            },
            "rotation": {
              "default": None,
              "description": "The rotation of the image in degrees.",
              "nullable": True,
              "title": "Rotation",
              "type": "integer"
            },
            "sensor": {
              "default": None,
              "description": "The sensor used to create the image.",
              "nullable": True,
              "title": "Sensor",
              "type": "string"
            },
            "state": {
              "default": None,
              "description": "The state or region in which the photo was taken.",
              "nullable": True,
              "title": "State",
              "type": "string"
            },
            "subjectDistance": {
              "default": None,
              "description": "The subject distance of the image.",
              "nullable": True,
              "title": "Subject Distance",
              "type": "integer"
            },
            "time": {
              "default": None,
              "description": "The time the photo was taken (Exif DateTime).",
              "nullable": True,
              "title": "Time",
              "type": "string"
            },
            "whiteBalance": {
              "default": None,
              "description": "The white balance mode used to create the image.",
              "nullable": True,
              "title": "White Balance",
              "type": "string"
            },
            "width": {
              "default": None,
              "description": "The width of the image in pixels.",
              "nullable": True,
              "title": "Width",
              "type": "integer"
            }
          },
          "title": "ImageMediaMetadata",
          "type": "object"
        },
        "isAppAuthorized": {
          "default": None,
          "description": "Whether the file was created or opened by the requesting app.",
          "nullable": True,
          "title": "Is App Authorized",
          "type": "boolean"
        },
        "kind": {
          "description": "Identifies the resource type. This is always 'drive#file'.",
          "title": "Kind",
          "type": "string"
        },
        "labelInfo": {
          "additionalProperties": False,
          "default": None,
          "description": "Information about labels applied to the file.",
          "nullable": True,
          "properties": {
            "labels": {
              "default": None,
              "items": {
                "properties": {
                  "fields": {
                    "additionalProperties": {
                      "properties": {
                        "dateString": {
                          "anyOf": [
                            {
                              "items": {
                                "type": "string"
                              },
                              "type": "array"
                            },
                            {
                              "type": "null"
                            }
                          ],
                          "default": None,
                          "title": "Datestring"
                        },
                        "id": {
                          "anyOf": [
                            {
                              "type": "string"
                            },
                            {
                              "type": "null"
                            }
                          ],
                          "default": None,
                          "title": "Id"
                        },
                        "integer": {
                          "anyOf": [
                            {
                              "items": {
                                "type": "string"
                              },
                              "type": "array"
                            },
                            {
                              "type": "null"
                            }
                          ],
                          "default": None,
                          "title": "Integer"
                        },
                        "kind": {
                          "anyOf": [
                            {
                              "type": "string"
                            },
                            {
                              "type": "null"
                            }
                          ],
                          "default": None,
                          "title": "Kind"
                        },
                        "selection": {
                          "anyOf": [
                            {
                              "items": {
                                "type": "string"
                              },
                              "type": "array"
                            },
                            {
                              "type": "null"
                            }
                          ],
                          "default": None,
                          "title": "Selection"
                        },
                        "text": {
                          "anyOf": [
                            {
                              "items": {
                                "type": "string"
                              },
                              "type": "array"
                            },
                            {
                              "type": "null"
                            }
                          ],
                          "default": None,
                          "title": "Text"
                        },
                        "user": {
                          "anyOf": [
                            {
                              "items": {
                                "type": "string"
                              },
                              "type": "array"
                            },
                            {
                              "type": "null"
                            }
                          ],
                          "default": None,
                          "title": "User"
                        },
                        "valueType": {
                          "anyOf": [
                            {
                              "type": "string"
                            },
                            {
                              "type": "null"
                            }
                          ],
                          "default": None,
                          "title": "Valuetype"
                        }
                      },
                      "title": "LabelField",
                      "type": "object"
                    },
                    "default": None,
                    "nullable": True,
                    "title": "Fields",
                    "type": "object"
                  },
                  "id": {
                    "default": None,
                    "nullable": True,
                    "title": "Id",
                    "type": "string"
                  },
                  "kind": {
                    "default": None,
                    "nullable": True,
                    "title": "Kind",
                    "type": "string"
                  },
                  "revisionId": {
                    "default": None,
                    "nullable": True,
                    "title": "Revision Id",
                    "type": "string"
                  }
                },
                "title": "Label",
                "type": "object"
              },
              "nullable": True,
              "title": "Labels",
              "type": "array"
            }
          },
          "title": "LabelInfo",
          "type": "object"
        },
        "lastModifyingUser": {
          "additionalProperties": False,
          "default": None,
          "description": "The last user to modify the file.",
          "nullable": True,
          "properties": {
            "displayName": {
              "default": None,
              "description": "The user's display name.",
              "nullable": True,
              "title": "Display Name",
              "type": "string"
            },
            "emailAddress": {
              "default": None,
              "description": "The user's email address.",
              "nullable": True,
              "title": "Email Address",
              "type": "string"
            },
            "kind": {
              "default": None,
              "description": "Resource type. Always 'drive#user'.",
              "nullable": True,
              "title": "Kind",
              "type": "string"
            },
            "me": {
              "default": None,
              "description": "Whether this user is the authenticated user.",
              "nullable": True,
              "title": "Me",
              "type": "boolean"
            },
            "photoLink": {
              "default": None,
              "description": "A link to the user's profile photo.",
              "nullable": True,
              "title": "Photo Link",
              "type": "string"
            }
          },
          "title": "User",
          "type": "object"
        },
        "linkShareMetadata": {
          "additionalProperties": False,
          "default": None,
          "description": "Metadata about the shared link for this file.",
          "nullable": True,
          "properties": {
            "securityUpdateApplied": {
              "default": None,
              "description": "Whether the security update has been applied to the file.",
              "nullable": True,
              "title": "Security Update Applied",
              "type": "boolean"
            },
            "securityUpdateEligible": {
              "default": None,
              "description": "Whether the file is eligible for the security update.",
              "nullable": True,
              "title": "Security Update Eligible",
              "type": "boolean"
            }
          },
          "title": "LinkShareMetadata",
          "type": "object"
        },
        "md5Checksum": {
          "default": None,
          "description": "The MD5 checksum for the content of the file. This is only applicable to files with binary content in Google Drive.",
          "nullable": True,
          "title": "Md5 Checksum",
          "type": "string"
        },
        "mimeType": {
          "default": None,
          "description": "The MIME type of the file.",
          "nullable": True,
          "title": "Mime Type",
          "type": "string"
        },
        "modifiedByMe": {
          "default": None,
          "description": "Whether the file has been modified by this user.",
          "nullable": True,
          "title": "Modified By Me",
          "type": "boolean"
        },
        "modifiedByMeTime": {
          "default": None,
          "description": "The last time the file was modified by the user (RFC 3339 date-time).",
          "nullable": True,
          "title": "Modified By Me Time",
          "type": "string"
        },
        "modifiedTime": {
          "default": None,
          "description": "The last time the file was modified by anyone (RFC 3339 date-time).",
          "nullable": True,
          "title": "Modified Time",
          "type": "string"
        },
        "name": {
          "default": None,
          "description": "The name of the file.",
          "nullable": True,
          "title": "Name",
          "type": "string"
        },
        "originalFilename": {
          "default": None,
          "description": "The original filename of the uploaded content if available, or else the original value of the name field. Once set, it will only change if a new revision is uploaded.",
          "nullable": True,
          "title": "Original Filename",
          "type": "string"
        },
        "ownedByMe": {
          "default": None,
          "description": "Whether the user owns the file.",
          "nullable": True,
          "title": "Owned By Me",
          "type": "boolean"
        },
        "owners": {
          "default": None,
          "description": "The owners of the file. Currently, only certain legacy files may have more than one owner.",
          "items": {
            "properties": {
              "displayName": {
                "default": None,
                "description": "The user's display name.",
                "nullable": True,
                "title": "Display Name",
                "type": "string"
              },
              "emailAddress": {
                "default": None,
                "description": "The user's email address.",
                "nullable": True,
                "title": "Email Address",
                "type": "string"
              },
              "kind": {
                "default": None,
                "description": "Resource type. Always 'drive#user'.",
                "nullable": True,
                "title": "Kind",
                "type": "string"
              },
              "me": {
                "default": None,
                "description": "Whether this user is the authenticated user.",
                "nullable": True,
                "title": "Me",
                "type": "boolean"
              },
              "photoLink": {
                "default": None,
                "description": "A link to the user's profile photo.",
                "nullable": True,
                "title": "Photo Link",
                "type": "string"
              }
            },
            "title": "User",
            "type": "object"
          },
          "nullable": True,
          "title": "Owners",
          "type": "array"
        },
        "parents": {
          "default": None,
          "description": "The IDs of the parent folders which contain the file.",
          "items": {
            "properties": {},
            "type": "string"
          },
          "nullable": True,
          "title": "Parents",
          "type": "array"
        },
        "permissionIds": {
          "default": None,
          "description": "A list of permission IDs for users with access to this file.",
          "items": {
            "properties": {},
            "type": "string"
          },
          "nullable": True,
          "title": "Permission Ids",
          "type": "array"
        },
        "permissions": {
          "default": None,
          "description": "The permissions for the file. This field is only populated for items in shared drives.",
          "items": {
            "properties": {
              "displayName": {
                "default": None,
                "nullable": True,
                "title": "Display Name",
                "type": "string"
              },
              "emailAddress": {
                "default": None,
                "nullable": True,
                "title": "Email Address",
                "type": "string"
              },
              "id": {
                "default": None,
                "nullable": True,
                "title": "Id",
                "type": "string"
              },
              "kind": {
                "default": "drive#permission",
                "nullable": True,
                "title": "Kind",
                "type": "string"
              },
              "role": {
                "default": None,
                "nullable": True,
                "title": "Role",
                "type": "string"
              },
              "type": {
                "default": None,
                "nullable": True,
                "title": "Type",
                "type": "string"
              }
            },
            "title": "Permission",
            "type": "object"
          },
          "nullable": True,
          "title": "Permissions",
          "type": "array"
        },
        "properties": {
          "additionalProperties": {
            "type": "string"
          },
          "default": None,
          "description": "A collection of arbitrary key-value pairs which are visible to all apps.",
          "nullable": True,
          "title": "Properties",
          "type": "object"
        },
        "quotaBytesUsed": {
          "default": None,
          "description": "The number of bytes the file occupies in storage. This is only applicable to files with binary content in Google Drive.",
          "nullable": True,
          "title": "Quota Bytes Used",
          "type": "string"
        },
        "resourceKey": {
          "default": None,
          "description": "A key needed to access the item via a shared link.",
          "nullable": True,
          "title": "Resource Key",
          "type": "string"
        },
        "sha1Checksum": {
          "default": None,
          "description": "The SHA1 checksum for the content of the file. This is only applicable to files with binary content in Google Drive.",
          "nullable": True,
          "title": "Sha1 Checksum",
          "type": "string"
        },
        "sha256Checksum": {
          "default": None,
          "description": "The SHA256 checksum for the content of the file. This is only applicable to files with binary content in Google Drive.",
          "nullable": True,
          "title": "Sha256 Checksum",
          "type": "string"
        },
        "shared": {
          "default": None,
          "description": "Whether the file has been shared.",
          "nullable": True,
          "title": "Shared",
          "type": "boolean"
        },
        "sharedWithMeTime": {
          "default": None,
          "description": "The time at which the file was shared with the user (RFC 3339 date-time).",
          "nullable": True,
          "title": "Shared With Me Time",
          "type": "string"
        },
        "sharingUser": {
          "additionalProperties": False,
          "default": None,
          "description": "The user who shared the file with the current user, if applicable.",
          "nullable": True,
          "properties": {
            "displayName": {
              "default": None,
              "description": "The user's display name.",
              "nullable": True,
              "title": "Display Name",
              "type": "string"
            },
            "emailAddress": {
              "default": None,
              "description": "The user's email address.",
              "nullable": True,
              "title": "Email Address",
              "type": "string"
            },
            "kind": {
              "default": None,
              "description": "Resource type. Always 'drive#user'.",
              "nullable": True,
              "title": "Kind",
              "type": "string"
            },
            "me": {
              "default": None,
              "description": "Whether this user is the authenticated user.",
              "nullable": True,
              "title": "Me",
              "type": "boolean"
            },
            "photoLink": {
              "default": None,
              "description": "A link to the user's profile photo.",
              "nullable": True,
              "title": "Photo Link",
              "type": "string"
            }
          },
          "title": "User",
          "type": "object"
        },
        "shortcutDetails": {
          "additionalProperties": False,
          "default": None,
          "description": "Shortcut file details. Only populated for shortcut files, which have the mimeType field set to application/vnd.google-apps.shortcut.",
          "nullable": True,
          "properties": {
            "targetId": {
              "default": None,
              "description": "The ID of the file that this shortcut points to.",
              "nullable": True,
              "title": "Target Id",
              "type": "string"
            },
            "targetMimeType": {
              "default": None,
              "description": "The MIME type of the file that this shortcut points to.",
              "nullable": True,
              "title": "Target Mime Type",
              "type": "string"
            },
            "targetResourceKey": {
              "default": None,
              "description": "The resource key of the target file.",
              "nullable": True,
              "title": "Target Resource Key",
              "type": "string"
            }
          },
          "title": "ShortcutDetails",
          "type": "object"
        },
        "size": {
          "default": None,
          "description": "The size of the file's content in bytes. This is applicable to files with binary content in Google Drive and Google Docs files.",
          "nullable": True,
          "title": "Size",
          "type": "string"
        },
        "spaces": {
          "default": None,
          "description": "The list of spaces which contain the file. The currently supported values are 'drive', 'appDataFolder' and 'photos'.",
          "items": {
            "properties": {},
            "type": "string"
          },
          "nullable": True,
          "title": "Spaces",
          "type": "array"
        },
        "starred": {
          "default": None,
          "description": "Whether the user has starred the file.",
          "nullable": True,
          "title": "Starred",
          "type": "boolean"
        },
        "teamDriveId": {
          "default": None,
          "description": "Deprecated: Use driveId instead.",
          "nullable": True,
          "title": "Team Drive Id",
          "type": "string"
        },
        "thumbnailLink": {
          "default": None,
          "description": "A short-lived link to the file's thumbnail. Typically lasts on the order of hours. Only populated when the requesting app can access the file's content.",
          "nullable": True,
          "title": "Thumbnail Link",
          "type": "string"
        },
        "thumbnailVersion": {
          "default": None,
          "description": "The version of the file's thumbnail. Available when the media is hosted on Google Drive.",
          "nullable": True,
          "title": "Thumbnail Version",
          "type": "string"
        },
        "trashed": {
          "default": None,
          "description": "Whether the file has been trashed, either explicitly or from a trashed parent folder.",
          "nullable": True,
          "title": "Trashed",
          "type": "boolean"
        },
        "trashedTime": {
          "default": None,
          "nullable": True,
          "title": "Trashed Time",
          "type": "string"
        },
        "trashingUser": {
          "additionalProperties": False,
          "default": None,
          "nullable": True,
          "properties": {
            "displayName": {
              "default": None,
              "description": "The user's display name.",
              "nullable": True,
              "title": "Display Name",
              "type": "string"
            },
            "emailAddress": {
              "default": None,
              "description": "The user's email address.",
              "nullable": True,
              "title": "Email Address",
              "type": "string"
            },
            "kind": {
              "default": None,
              "description": "Resource type. Always 'drive#user'.",
              "nullable": True,
              "title": "Kind",
              "type": "string"
            },
            "me": {
              "default": None,
              "description": "Whether this user is the authenticated user.",
              "nullable": True,
              "title": "Me",
              "type": "boolean"
            },
            "photoLink": {
              "default": None,
              "description": "A link to the user's profile photo.",
              "nullable": True,
              "title": "Photo Link",
              "type": "string"
            }
          },
          "title": "User",
          "type": "object"
        },
        "version": {
          "default": None,
          "description": "A monotonically increasing version number for the file. This reflects every change made to the file on the server, even those not visible to the user.",
          "nullable": True,
          "title": "Version",
          "type": "string"
        },
        "videoMediaMetadata": {
          "additionalProperties": False,
          "default": None,
          "description": "Additional metadata about video media, if available.",
          "nullable": True,
          "properties": {
            "durationMillis": {
              "default": None,
              "description": "The duration of the video in milliseconds.",
              "nullable": True,
              "title": "Duration Millis",
              "type": "string"
            },
            "height": {
              "default": None,
              "description": "The height of the video in pixels.",
              "nullable": True,
              "title": "Height",
              "type": "integer"
            },
            "width": {
              "default": None,
              "description": "The width of the video in pixels.",
              "nullable": True,
              "title": "Width",
              "type": "integer"
            }
          },
          "title": "VideoMediaMetadata",
          "type": "object"
        },
        "viewedByMe": {
          "default": None,
          "description": "Whether the file has been viewed by this user.",
          "nullable": True,
          "title": "Viewed By Me",
          "type": "boolean"
        },
        "viewedByMeTime": {
          "default": None,
          "description": "The last time the file was viewed by the user (RFC 3339 date-time).",
          "nullable": True,
          "title": "Viewed By Me Time",
          "type": "string"
        },
        "viewersCanCopyContent": {
          "default": None,
          "description": "Whether users with only reader or commenter permission can copy the content of the file. This does not apply to Google Docs, Sheets, and Slides.",
          "nullable": True,
          "title": "Viewers Can Copy Content",
          "type": "boolean"
        },
        "webContentLink": {
          "default": None,
          "description": "A link for downloading the content of the file in a browser. This is only available for files with binary content in Google Drive.",
          "nullable": True,
          "title": "Web Content Link",
          "type": "string"
        },
        "webViewLink": {
          "default": None,
          "description": "A link for opening the file in a relevant Google editor or viewer in a browser.",
          "nullable": True,
          "title": "Web View Link",
          "type": "string"
        },
        "writersCanShare": {
          "default": None,
          "description": "Whether writers can share the document with other users.",
          "nullable": True,
          "title": "Writers Can Share",
          "type": "boolean"
        }
      },
      "required": [
        "kind",
        "id"
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
  "title": "UploadFileResponseWrapper",
  "type": "object"
}