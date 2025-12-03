slack_post_message_output_schema = {
  "properties": {
    "data": {
      "additionalProperties": False,
      "description": "Data from the action execution",
      "properties": {
        "action": {
          "additionalProperties": False,
          "default": None,
          "description": "Represents an interactive element (e.g., button) action payload returned when interactive_blocks are used.",
          "nullable": True,
          "properties": {
            "action_id": {
              "title": "Action Id",
              "type": "string"
            },
            "action_ts": {
              "default": None,
              "nullable": True,
              "title": "Action Ts",
              "type": "string"
            },
            "block_id": {
              "default": None,
              "nullable": True,
              "title": "Block Id",
              "type": "string"
            },
            "text": {
              "additionalProperties": False,
              "default": None,
              "nullable": True,
              "properties": {
                "emoji": {
                  "default": None,
                  "nullable": True,
                  "title": "Emoji",
                  "type": "boolean"
                },
                "text": {
                  "title": "Text",
                  "type": "string"
                },
                "type": {
                  "title": "Type",
                  "type": "string"
                }
              },
              "required": [
                "type",
                "text"
              ],
              "title": "TextObject",
              "type": "object"
            },
            "type": {
              "title": "Type",
              "type": "string"
            },
            "value": {
              "default": None,
              "nullable": True,
              "title": "Value",
              "type": "string"
            }
          },
          "required": [
            "action_id",
            "type"
          ],
          "title": "InteractiveAction",
          "type": "object"
        },
        "channel": {
          "default": None,
          "description": "ID of the conversation where the message was posted (e.g., C123ABC456). Present when ok is true.",
          "nullable": True,
          "title": "Channel",
          "type": "string"
        },
        "deprecated_argument": {
          "default": None,
          "description": "Name of an argument that is deprecated, when Slack indicates deprecation in the response.",
          "nullable": True,
          "title": "Deprecated Argument",
          "type": "string"
        },
        "error": {
          "default": None,
          "description": "Error code string describing why the request failed. Present when ok is false.",
          "nullable": True,
          "title": "Error",
          "type": "string"
        },
        "errors": {
          "default": None,
          "description": "Array of error strings when multiple errors are returned.",
          "items": {
            "properties": {},
            "type": "string"
          },
          "nullable": True,
          "title": "Errors",
          "type": "array"
        },
        "interactivity": {
          "additionalProperties": True,
          "default": None,
          "description": "Interactivity context object when interactive elements are involved (structure varies).",
          "nullable": True,
          "title": "Interactivity",
          "type": "object"
        },
        "message": {
          "additionalProperties": False,
          "default": None,
          "description": "The complete message object as stored by Slack after parsing/sanitization. Present when ok is true.",
          "nullable": True,
          "properties": {
            "app_id": {
              "default": None,
              "description": "App ID associated with the message.",
              "nullable": True,
              "title": "App Id",
              "type": "string"
            },
            "attachments": {
              "default": None,
              "description": "A list of attachment objects, if any were included in the message.",
              "items": {
                "properties": {
                  "fallback": {
                    "default": None,
                    "nullable": True,
                    "title": "Fallback",
                    "type": "string"
                  },
                  "id": {
                    "title": "Id",
                    "type": "integer"
                  },
                  "image_bytes": {
                    "default": None,
                    "nullable": True,
                    "title": "Image Bytes",
                    "type": "integer"
                  },
                  "image_height": {
                    "default": None,
                    "nullable": True,
                    "title": "Image Height",
                    "type": "integer"
                  },
                  "image_url": {
                    "default": None,
                    "nullable": True,
                    "title": "Image Url",
                    "type": "string"
                  },
                  "image_width": {
                    "default": None,
                    "nullable": True,
                    "title": "Image Width",
                    "type": "integer"
                  }
                },
                "required": [
                  "id"
                ],
                "title": "Attachment",
                "type": "object"
              },
              "minItems": 1,
              "nullable": True,
              "title": "Attachments",
              "type": "array"
            },
            "blocks": {
              "default": None,
              "description": "An array of Block Kit layout blocks that define the message's structure and appearance. For details on block structure, refer to the Slack API Block Kit documentation.",
              "items": {
                "additionalProperties": True,
                "properties": {
                  "type": {
                    "title": "Type",
                    "type": "string"
                  }
                },
                "required": [
                  "type"
                ],
                "title": "Block",
                "type": "object"
              },
              "nullable": True,
              "title": "Blocks",
              "type": "array"
            },
            "bot_id": {
              "default": None,
              "description": "ID of the bot that authored the message, when the message was posted by a bot.",
              "nullable": True,
              "title": "Bot Id",
              "type": "string"
            },
            "bot_profile": {
              "additionalProperties": False,
              "default": None,
              "description": "Profile information for the bot user that posted this message, if applicable and available.",
              "nullable": True,
              "properties": {
                "app_id": {
                  "pattern": "^A[A-Z0-9]{1,}$",
                  "title": "App Id",
                  "type": "string"
                },
                "deleted": {
                  "title": "Deleted",
                  "type": "boolean"
                },
                "icons": {
                  "additionalProperties": False,
                  "properties": {
                    "image_36": {
                      "format": "uri",
                      "minLength": 1,
                      "title": "Image 36",
                      "type": "string"
                    },
                    "image_48": {
                      "format": "uri",
                      "minLength": 1,
                      "title": "Image 48",
                      "type": "string"
                    },
                    "image_72": {
                      "format": "uri",
                      "minLength": 1,
                      "title": "Image 72",
                      "type": "string"
                    }
                  },
                  "required": [
                    "image_36",
                    "image_48",
                    "image_72"
                  ],
                  "title": "Icons",
                  "type": "object"
                },
                "id": {
                  "pattern": "^B[A-Z0-9]{8,}$",
                  "title": "Id",
                  "type": "string"
                },
                "name": {
                  "title": "Name",
                  "type": "string"
                },
                "team_id": {
                  "pattern": "^[T][A-Z0-9]{2,}$",
                  "title": "Team Id",
                  "type": "string"
                },
                "updated": {
                  "title": "Updated",
                  "type": "integer"
                }
              },
              "required": [
                "app_id",
                "deleted",
                "icons",
                "id",
                "name",
                "team_id",
                "updated"
              ],
              "title": "BotProfile",
              "type": "object"
            },
            "client_msg_id": {
              "default": None,
              "description": "A unique identifier for the message, specified by the client. Can be used to aid in de-duplication.",
              "nullable": True,
              "title": "Client Msg Id",
              "type": "string"
            },
            "comment": {
              "additionalProperties": False,
              "default": None,
              "description": "If this message is a file comment, this field contains the comment details.",
              "nullable": True,
              "properties": {
                "comment": {
                  "title": "Comment",
                  "type": "string"
                },
                "created": {
                  "title": "Created",
                  "type": "integer"
                },
                "id": {
                  "pattern": "^Fc[A-Z0-9]{8,}$",
                  "title": "Id",
                  "type": "string"
                },
                "is_intro": {
                  "title": "Is Intro",
                  "type": "boolean"
                },
                "is_starred": {
                  "default": None,
                  "nullable": True,
                  "title": "Is Starred",
                  "type": "boolean"
                },
                "num_stars": {
                  "default": None,
                  "nullable": True,
                  "title": "Num Stars",
                  "type": "integer"
                },
                "pinned_info": {
                  "additionalProperties": True,
                  "default": None,
                  "nullable": True,
                  "title": "Pinned Info",
                  "type": "object"
                },
                "pinned_to": {
                  "default": None,
                  "items": {
                    "pattern": "^[CGD][A-Z0-9]{8,}$",
                    "properties": {},
                    "title": "PinnedToItem",
                    "type": "string"
                  },
                  "nullable": True,
                  "title": "Pinned To",
                  "type": "array"
                },
                "reactions": {
                  "default": None,
                  "items": {
                    "additionalProperties": True,
                    "properties": {
                      "count": {
                        "title": "Count",
                        "type": "integer"
                      },
                      "name": {
                        "title": "Name",
                        "type": "string"
                      },
                      "users": {
                        "items": {
                          "pattern": "^[UW][A-Z0-9]{2,}$",
                          "properties": {},
                          "title": "User",
                          "type": "string"
                        },
                        "title": "Users",
                        "type": "array"
                      }
                    },
                    "required": [
                      "count",
                      "name",
                      "users"
                    ],
                    "title": "Reaction",
                    "type": "object"
                  },
                  "nullable": True,
                  "title": "Reactions",
                  "type": "array"
                },
                "timestamp": {
                  "title": "Timestamp",
                  "type": "integer"
                },
                "user": {
                  "pattern": "^[UW][A-Z0-9]{2,}$",
                  "title": "User",
                  "type": "string"
                }
              },
              "required": [
                "comment",
                "created",
                "id",
                "is_intro",
                "timestamp",
                "user"
              ],
              "title": "Comment",
              "type": "object"
            },
            "display_as_bot": {
              "default": None,
              "description": "Indicates if the message is displayed as if it were posted by a bot, even if posted by a user.",
              "nullable": True,
              "title": "Display As Bot",
              "type": "boolean"
            },
            "file": {
              "additionalProperties": False,
              "default": None,
              "description": "If the message contains a single file, this object provides details about the file.",
              "nullable": True,
              "properties": {
                "channels": {
                  "default": None,
                  "items": {
                    "pattern": "^[C][A-Z0-9]{2,}$",
                    "properties": {},
                    "title": "Channel",
                    "type": "string"
                  },
                  "nullable": True,
                  "title": "Channels",
                  "type": "array"
                },
                "comments_count": {
                  "default": None,
                  "nullable": True,
                  "title": "Comments Count",
                  "type": "integer"
                },
                "created": {
                  "default": None,
                  "nullable": True,
                  "title": "Created",
                  "type": "integer"
                },
                "date_delete": {
                  "default": None,
                  "nullable": True,
                  "title": "Date Delete",
                  "type": "integer"
                },
                "display_as_bot": {
                  "default": None,
                  "nullable": True,
                  "title": "Display As Bot",
                  "type": "boolean"
                },
                "editable": {
                  "default": None,
                  "nullable": True,
                  "title": "Editable",
                  "type": "boolean"
                },
                "editor": {
                  "default": None,
                  "nullable": True,
                  "pattern": "^[UW][A-Z0-9]{2,}$",
                  "title": "Editor",
                  "type": "string"
                },
                "external_id": {
                  "default": None,
                  "nullable": True,
                  "title": "External Id",
                  "type": "string"
                },
                "external_type": {
                  "default": None,
                  "nullable": True,
                  "title": "External Type",
                  "type": "string"
                },
                "external_url": {
                  "default": None,
                  "format": "uri",
                  "minLength": 1,
                  "nullable": True,
                  "title": "External Url",
                  "type": "string"
                },
                "filetype": {
                  "default": None,
                  "nullable": True,
                  "title": "Filetype",
                  "type": "string"
                },
                "groups": {
                  "default": None,
                  "items": {
                    "pattern": "^[G][A-Z0-9]{8,}$",
                    "properties": {},
                    "title": "Group",
                    "type": "string"
                  },
                  "nullable": True,
                  "title": "Groups",
                  "type": "array"
                },
                "has_rich_preview": {
                  "default": None,
                  "nullable": True,
                  "title": "Has Rich Preview",
                  "type": "boolean"
                },
                "id": {
                  "default": None,
                  "nullable": True,
                  "pattern": "^[F][A-Z0-9]{8,}$",
                  "title": "Id",
                  "type": "string"
                },
                "image_exif_rotation": {
                  "default": None,
                  "nullable": True,
                  "title": "Image Exif Rotation",
                  "type": "integer"
                },
                "ims": {
                  "default": None,
                  "items": {
                    "pattern": "^[D][A-Z0-9]{8,}$",
                    "properties": {},
                    "title": "Im",
                    "type": "string"
                  },
                  "nullable": True,
                  "title": "Ims",
                  "type": "array"
                },
                "is_external": {
                  "default": None,
                  "nullable": True,
                  "title": "Is External",
                  "type": "boolean"
                },
                "is_public": {
                  "default": None,
                  "nullable": True,
                  "title": "Is Public",
                  "type": "boolean"
                },
                "is_starred": {
                  "default": None,
                  "nullable": True,
                  "title": "Is Starred",
                  "type": "boolean"
                },
                "is_tombstoned": {
                  "default": None,
                  "nullable": True,
                  "title": "Is Tombstoned",
                  "type": "boolean"
                },
                "last_editor": {
                  "default": None,
                  "nullable": True,
                  "pattern": "^[UW][A-Z0-9]{2,}$",
                  "title": "Last Editor",
                  "type": "string"
                },
                "mimetype": {
                  "default": None,
                  "nullable": True,
                  "title": "Mimetype",
                  "type": "string"
                },
                "mode": {
                  "default": None,
                  "nullable": True,
                  "title": "Mode",
                  "type": "string"
                },
                "name": {
                  "default": None,
                  "nullable": True,
                  "title": "Name",
                  "type": "string"
                },
                "non_owner_editable": {
                  "default": None,
                  "nullable": True,
                  "title": "Non Owner Editable",
                  "type": "boolean"
                },
                "num_stars": {
                  "default": None,
                  "nullable": True,
                  "title": "Num Stars",
                  "type": "integer"
                },
                "original_h": {
                  "default": None,
                  "nullable": True,
                  "title": "Original H",
                  "type": "integer"
                },
                "original_w": {
                  "default": None,
                  "nullable": True,
                  "title": "Original W",
                  "type": "integer"
                },
                "permalink": {
                  "default": None,
                  "format": "uri",
                  "minLength": 1,
                  "nullable": True,
                  "title": "Permalink",
                  "type": "string"
                },
                "permalink_public": {
                  "default": None,
                  "format": "uri",
                  "minLength": 1,
                  "nullable": True,
                  "title": "Permalink Public",
                  "type": "string"
                },
                "pinned_info": {
                  "additionalProperties": True,
                  "default": None,
                  "nullable": True,
                  "title": "Pinned Info",
                  "type": "object"
                },
                "pinned_to": {
                  "default": None,
                  "items": {
                    "pattern": "^[CGD][A-Z0-9]{8,}$",
                    "properties": {},
                    "title": "PinnedToItem",
                    "type": "string"
                  },
                  "nullable": True,
                  "title": "Pinned To",
                  "type": "array"
                },
                "pretty_type": {
                  "default": None,
                  "nullable": True,
                  "title": "Pretty Type",
                  "type": "string"
                },
                "preview": {
                  "default": None,
                  "nullable": True,
                  "title": "Preview",
                  "type": "string"
                },
                "public_url_shared": {
                  "default": None,
                  "nullable": True,
                  "title": "Public Url Shared",
                  "type": "boolean"
                },
                "reactions": {
                  "default": None,
                  "items": {
                    "additionalProperties": True,
                    "properties": {
                      "count": {
                        "title": "Count",
                        "type": "integer"
                      },
                      "name": {
                        "title": "Name",
                        "type": "string"
                      },
                      "users": {
                        "items": {
                          "pattern": "^[UW][A-Z0-9]{2,}$",
                          "properties": {},
                          "title": "User",
                          "type": "string"
                        },
                        "title": "Users",
                        "type": "array"
                      }
                    },
                    "required": [
                      "count",
                      "name",
                      "users"
                    ],
                    "title": "Reaction",
                    "type": "object"
                  },
                  "nullable": True,
                  "title": "Reactions",
                  "type": "array"
                },
                "shares": {
                  "additionalProperties": False,
                  "default": None,
                  "nullable": True,
                  "properties": {
                    "private": {
                      "default": None,
                      "nullable": True,
                      "title": "Private"
                    },
                    "public": {
                      "default": None,
                      "nullable": True,
                      "title": "Public"
                    }
                  },
                  "title": "Shares",
                  "type": "object"
                },
                "size": {
                  "default": None,
                  "nullable": True,
                  "title": "Size",
                  "type": "integer"
                },
                "source_team": {
                  "default": None,
                  "nullable": True,
                  "pattern": "^[T][A-Z0-9]{2,}$",
                  "title": "Source Team",
                  "type": "string"
                },
                "state": {
                  "default": None,
                  "nullable": True,
                  "title": "State",
                  "type": "string"
                },
                "thumb_1024": {
                  "default": None,
                  "format": "uri",
                  "minLength": 1,
                  "nullable": True,
                  "title": "Thumb 1024",
                  "type": "string"
                },
                "thumb_1024_h": {
                  "default": None,
                  "nullable": True,
                  "title": "Thumb 1024 H",
                  "type": "integer"
                },
                "thumb_1024_w": {
                  "default": None,
                  "nullable": True,
                  "title": "Thumb 1024 W",
                  "type": "integer"
                },
                "thumb_160": {
                  "default": None,
                  "format": "uri",
                  "minLength": 1,
                  "nullable": True,
                  "title": "Thumb 160",
                  "type": "string"
                },
                "thumb_360": {
                  "default": None,
                  "format": "uri",
                  "minLength": 1,
                  "nullable": True,
                  "title": "Thumb 360",
                  "type": "string"
                },
                "thumb_360_h": {
                  "default": None,
                  "nullable": True,
                  "title": "Thumb 360 H",
                  "type": "integer"
                },
                "thumb_360_w": {
                  "default": None,
                  "nullable": True,
                  "title": "Thumb 360 W",
                  "type": "integer"
                },
                "thumb_480": {
                  "default": None,
                  "format": "uri",
                  "minLength": 1,
                  "nullable": True,
                  "title": "Thumb 480",
                  "type": "string"
                },
                "thumb_480_h": {
                  "default": None,
                  "nullable": True,
                  "title": "Thumb 480 H",
                  "type": "integer"
                },
                "thumb_480_w": {
                  "default": None,
                  "nullable": True,
                  "title": "Thumb 480 W",
                  "type": "integer"
                },
                "thumb_64": {
                  "default": None,
                  "format": "uri",
                  "minLength": 1,
                  "nullable": True,
                  "title": "Thumb 64",
                  "type": "string"
                },
                "thumb_720": {
                  "default": None,
                  "format": "uri",
                  "minLength": 1,
                  "nullable": True,
                  "title": "Thumb 720",
                  "type": "string"
                },
                "thumb_720_h": {
                  "default": None,
                  "nullable": True,
                  "title": "Thumb 720 H",
                  "type": "integer"
                },
                "thumb_720_w": {
                  "default": None,
                  "nullable": True,
                  "title": "Thumb 720 W",
                  "type": "integer"
                },
                "thumb_80": {
                  "default": None,
                  "format": "uri",
                  "minLength": 1,
                  "nullable": True,
                  "title": "Thumb 80",
                  "type": "string"
                },
                "thumb_800": {
                  "default": None,
                  "format": "uri",
                  "minLength": 1,
                  "nullable": True,
                  "title": "Thumb 800",
                  "type": "string"
                },
                "thumb_800_h": {
                  "default": None,
                  "nullable": True,
                  "title": "Thumb 800 H",
                  "type": "integer"
                },
                "thumb_800_w": {
                  "default": None,
                  "nullable": True,
                  "title": "Thumb 800 W",
                  "type": "integer"
                },
                "thumb_960": {
                  "default": None,
                  "format": "uri",
                  "minLength": 1,
                  "nullable": True,
                  "title": "Thumb 960",
                  "type": "string"
                },
                "thumb_960_h": {
                  "default": None,
                  "nullable": True,
                  "title": "Thumb 960 H",
                  "type": "integer"
                },
                "thumb_960_w": {
                  "default": None,
                  "nullable": True,
                  "title": "Thumb 960 W",
                  "type": "integer"
                },
                "thumb_tiny": {
                  "default": None,
                  "nullable": True,
                  "title": "Thumb Tiny",
                  "type": "string"
                },
                "timestamp": {
                  "default": None,
                  "nullable": True,
                  "title": "Timestamp",
                  "type": "integer"
                },
                "title": {
                  "default": None,
                  "nullable": True,
                  "title": "Title",
                  "type": "string"
                },
                "updated": {
                  "default": None,
                  "nullable": True,
                  "title": "Updated",
                  "type": "integer"
                },
                "url_private": {
                  "default": None,
                  "format": "uri",
                  "minLength": 1,
                  "nullable": True,
                  "title": "Url Private",
                  "type": "string"
                },
                "url_private_download": {
                  "default": None,
                  "format": "uri",
                  "minLength": 1,
                  "nullable": True,
                  "title": "Url Private Download",
                  "type": "string"
                },
                "user": {
                  "default": None,
                  "nullable": True,
                  "title": "User",
                  "type": "string"
                },
                "user_team": {
                  "default": None,
                  "nullable": True,
                  "pattern": "^[T][A-Z0-9]{2,}$",
                  "title": "User Team",
                  "type": "string"
                },
                "username": {
                  "default": None,
                  "nullable": True,
                  "title": "Username",
                  "type": "string"
                }
              },
              "title": "File",
              "type": "object"
            },
            "files": {
              "default": None,
              "description": "If the message contains multiple files, this list provides details for each file.",
              "items": {
                "properties": {
                  "channels": {
                    "default": None,
                    "items": {
                      "pattern": "^[C][A-Z0-9]{2,}$",
                      "properties": {},
                      "title": "Channel",
                      "type": "string"
                    },
                    "nullable": True,
                    "title": "Channels",
                    "type": "array"
                  },
                  "comments_count": {
                    "default": None,
                    "nullable": True,
                    "title": "Comments Count",
                    "type": "integer"
                  },
                  "created": {
                    "default": None,
                    "nullable": True,
                    "title": "Created",
                    "type": "integer"
                  },
                  "date_delete": {
                    "default": None,
                    "nullable": True,
                    "title": "Date Delete",
                    "type": "integer"
                  },
                  "display_as_bot": {
                    "default": None,
                    "nullable": True,
                    "title": "Display As Bot",
                    "type": "boolean"
                  },
                  "editable": {
                    "default": None,
                    "nullable": True,
                    "title": "Editable",
                    "type": "boolean"
                  },
                  "editor": {
                    "default": None,
                    "nullable": True,
                    "pattern": "^[UW][A-Z0-9]{2,}$",
                    "title": "Editor",
                    "type": "string"
                  },
                  "external_id": {
                    "default": None,
                    "nullable": True,
                    "title": "External Id",
                    "type": "string"
                  },
                  "external_type": {
                    "default": None,
                    "nullable": True,
                    "title": "External Type",
                    "type": "string"
                  },
                  "external_url": {
                    "default": None,
                    "format": "uri",
                    "minLength": 1,
                    "nullable": True,
                    "title": "External Url",
                    "type": "string"
                  },
                  "filetype": {
                    "default": None,
                    "nullable": True,
                    "title": "Filetype",
                    "type": "string"
                  },
                  "groups": {
                    "default": None,
                    "items": {
                      "pattern": "^[G][A-Z0-9]{8,}$",
                      "properties": {},
                      "title": "Group",
                      "type": "string"
                    },
                    "nullable": True,
                    "title": "Groups",
                    "type": "array"
                  },
                  "has_rich_preview": {
                    "default": None,
                    "nullable": True,
                    "title": "Has Rich Preview",
                    "type": "boolean"
                  },
                  "id": {
                    "default": None,
                    "nullable": True,
                    "pattern": "^[F][A-Z0-9]{8,}$",
                    "title": "Id",
                    "type": "string"
                  },
                  "image_exif_rotation": {
                    "default": None,
                    "nullable": True,
                    "title": "Image Exif Rotation",
                    "type": "integer"
                  },
                  "ims": {
                    "default": None,
                    "items": {
                      "pattern": "^[D][A-Z0-9]{8,}$",
                      "properties": {},
                      "title": "Im",
                      "type": "string"
                    },
                    "nullable": True,
                    "title": "Ims",
                    "type": "array"
                  },
                  "is_external": {
                    "default": None,
                    "nullable": True,
                    "title": "Is External",
                    "type": "boolean"
                  },
                  "is_public": {
                    "default": None,
                    "nullable": True,
                    "title": "Is Public",
                    "type": "boolean"
                  },
                  "is_starred": {
                    "default": None,
                    "nullable": True,
                    "title": "Is Starred",
                    "type": "boolean"
                  },
                  "is_tombstoned": {
                    "default": None,
                    "nullable": True,
                    "title": "Is Tombstoned",
                    "type": "boolean"
                  },
                  "last_editor": {
                    "default": None,
                    "nullable": True,
                    "pattern": "^[UW][A-Z0-9]{2,}$",
                    "title": "Last Editor",
                    "type": "string"
                  },
                  "mimetype": {
                    "default": None,
                    "nullable": True,
                    "title": "Mimetype",
                    "type": "string"
                  },
                  "mode": {
                    "default": None,
                    "nullable": True,
                    "title": "Mode",
                    "type": "string"
                  },
                  "name": {
                    "default": None,
                    "nullable": True,
                    "title": "Name",
                    "type": "string"
                  },
                  "non_owner_editable": {
                    "default": None,
                    "nullable": True,
                    "title": "Non Owner Editable",
                    "type": "boolean"
                  },
                  "num_stars": {
                    "default": None,
                    "nullable": True,
                    "title": "Num Stars",
                    "type": "integer"
                  },
                  "original_h": {
                    "default": None,
                    "nullable": True,
                    "title": "Original H",
                    "type": "integer"
                  },
                  "original_w": {
                    "default": None,
                    "nullable": True,
                    "title": "Original W",
                    "type": "integer"
                  },
                  "permalink": {
                    "default": None,
                    "format": "uri",
                    "minLength": 1,
                    "nullable": True,
                    "title": "Permalink",
                    "type": "string"
                  },
                  "permalink_public": {
                    "default": None,
                    "format": "uri",
                    "minLength": 1,
                    "nullable": True,
                    "title": "Permalink Public",
                    "type": "string"
                  },
                  "pinned_info": {
                    "additionalProperties": True,
                    "default": None,
                    "nullable": True,
                    "title": "Pinned Info",
                    "type": "object"
                  },
                  "pinned_to": {
                    "default": None,
                    "items": {
                      "pattern": "^[CGD][A-Z0-9]{8,}$",
                      "properties": {},
                      "title": "PinnedToItem",
                      "type": "string"
                    },
                    "nullable": True,
                    "title": "Pinned To",
                    "type": "array"
                  },
                  "pretty_type": {
                    "default": None,
                    "nullable": True,
                    "title": "Pretty Type",
                    "type": "string"
                  },
                  "preview": {
                    "default": None,
                    "nullable": True,
                    "title": "Preview",
                    "type": "string"
                  },
                  "public_url_shared": {
                    "default": None,
                    "nullable": True,
                    "title": "Public Url Shared",
                    "type": "boolean"
                  },
                  "reactions": {
                    "default": None,
                    "items": {
                      "additionalProperties": True,
                      "properties": {
                        "count": {
                          "title": "Count",
                          "type": "integer"
                        },
                        "name": {
                          "title": "Name",
                          "type": "string"
                        },
                        "users": {
                          "items": {
                            "pattern": "^[UW][A-Z0-9]{2,}$",
                            "properties": {},
                            "title": "User",
                            "type": "string"
                          },
                          "title": "Users",
                          "type": "array"
                        }
                      },
                      "required": [
                        "count",
                        "name",
                        "users"
                      ],
                      "title": "Reaction",
                      "type": "object"
                    },
                    "nullable": True,
                    "title": "Reactions",
                    "type": "array"
                  },
                  "shares": {
                    "additionalProperties": False,
                    "default": None,
                    "nullable": True,
                    "properties": {
                      "private": {
                        "default": None,
                        "nullable": True,
                        "title": "Private"
                      },
                      "public": {
                        "default": None,
                        "nullable": True,
                        "title": "Public"
                      }
                    },
                    "title": "Shares",
                    "type": "object"
                  },
                  "size": {
                    "default": None,
                    "nullable": True,
                    "title": "Size",
                    "type": "integer"
                  },
                  "source_team": {
                    "default": None,
                    "nullable": True,
                    "pattern": "^[T][A-Z0-9]{2,}$",
                    "title": "Source Team",
                    "type": "string"
                  },
                  "state": {
                    "default": None,
                    "nullable": True,
                    "title": "State",
                    "type": "string"
                  },
                  "thumb_1024": {
                    "default": None,
                    "format": "uri",
                    "minLength": 1,
                    "nullable": True,
                    "title": "Thumb 1024",
                    "type": "string"
                  },
                  "thumb_1024_h": {
                    "default": None,
                    "nullable": True,
                    "title": "Thumb 1024 H",
                    "type": "integer"
                  },
                  "thumb_1024_w": {
                    "default": None,
                    "nullable": True,
                    "title": "Thumb 1024 W",
                    "type": "integer"
                  },
                  "thumb_160": {
                    "default": None,
                    "format": "uri",
                    "minLength": 1,
                    "nullable": True,
                    "title": "Thumb 160",
                    "type": "string"
                  },
                  "thumb_360": {
                    "default": None,
                    "format": "uri",
                    "minLength": 1,
                    "nullable": True,
                    "title": "Thumb 360",
                    "type": "string"
                  },
                  "thumb_360_h": {
                    "default": None,
                    "nullable": True,
                    "title": "Thumb 360 H",
                    "type": "integer"
                  },
                  "thumb_360_w": {
                    "default": None,
                    "nullable": True,
                    "title": "Thumb 360 W",
                    "type": "integer"
                  },
                  "thumb_480": {
                    "default": None,
                    "format": "uri",
                    "minLength": 1,
                    "nullable": True,
                    "title": "Thumb 480",
                    "type": "string"
                  },
                  "thumb_480_h": {
                    "default": None,
                    "nullable": True,
                    "title": "Thumb 480 H",
                    "type": "integer"
                  },
                  "thumb_480_w": {
                    "default": None,
                    "nullable": True,
                    "title": "Thumb 480 W",
                    "type": "integer"
                  },
                  "thumb_64": {
                    "default": None,
                    "format": "uri",
                    "minLength": 1,
                    "nullable": True,
                    "title": "Thumb 64",
                    "type": "string"
                  },
                  "thumb_720": {
                    "default": None,
                    "format": "uri",
                    "minLength": 1,
                    "nullable": True,
                    "title": "Thumb 720",
                    "type": "string"
                  },
                  "thumb_720_h": {
                    "default": None,
                    "nullable": True,
                    "title": "Thumb 720 H",
                    "type": "integer"
                  },
                  "thumb_720_w": {
                    "default": None,
                    "nullable": True,
                    "title": "Thumb 720 W",
                    "type": "integer"
                  },
                  "thumb_80": {
                    "default": None,
                    "format": "uri",
                    "minLength": 1,
                    "nullable": True,
                    "title": "Thumb 80",
                    "type": "string"
                  },
                  "thumb_800": {
                    "default": None,
                    "format": "uri",
                    "minLength": 1,
                    "nullable": True,
                    "title": "Thumb 800",
                    "type": "string"
                  },
                  "thumb_800_h": {
                    "default": None,
                    "nullable": True,
                    "title": "Thumb 800 H",
                    "type": "integer"
                  },
                  "thumb_800_w": {
                    "default": None,
                    "nullable": True,
                    "title": "Thumb 800 W",
                    "type": "integer"
                  },
                  "thumb_960": {
                    "default": None,
                    "format": "uri",
                    "minLength": 1,
                    "nullable": True,
                    "title": "Thumb 960",
                    "type": "string"
                  },
                  "thumb_960_h": {
                    "default": None,
                    "nullable": True,
                    "title": "Thumb 960 H",
                    "type": "integer"
                  },
                  "thumb_960_w": {
                    "default": None,
                    "nullable": True,
                    "title": "Thumb 960 W",
                    "type": "integer"
                  },
                  "thumb_tiny": {
                    "default": None,
                    "nullable": True,
                    "title": "Thumb Tiny",
                    "type": "string"
                  },
                  "timestamp": {
                    "default": None,
                    "nullable": True,
                    "title": "Timestamp",
                    "type": "integer"
                  },
                  "title": {
                    "default": None,
                    "nullable": True,
                    "title": "Title",
                    "type": "string"
                  },
                  "updated": {
                    "default": None,
                    "nullable": True,
                    "title": "Updated",
                    "type": "integer"
                  },
                  "url_private": {
                    "default": None,
                    "format": "uri",
                    "minLength": 1,
                    "nullable": True,
                    "title": "Url Private",
                    "type": "string"
                  },
                  "url_private_download": {
                    "default": None,
                    "format": "uri",
                    "minLength": 1,
                    "nullable": True,
                    "title": "Url Private Download",
                    "type": "string"
                  },
                  "user": {
                    "default": None,
                    "nullable": True,
                    "title": "User",
                    "type": "string"
                  },
                  "user_team": {
                    "default": None,
                    "nullable": True,
                    "pattern": "^[T][A-Z0-9]{2,}$",
                    "title": "User Team",
                    "type": "string"
                  },
                  "username": {
                    "default": None,
                    "nullable": True,
                    "title": "Username",
                    "type": "string"
                  }
                },
                "title": "File",
                "type": "object"
              },
              "minItems": 1,
              "nullable": True,
              "title": "Files",
              "type": "array"
            },
            "icons": {
              "additionalProperties": False,
              "default": None,
              "description": "Icons associated with the message, such as the bot's icon or emoji.",
              "nullable": True,
              "properties": {
                "emoji": {
                  "default": None,
                  "nullable": True,
                  "title": "Emoji",
                  "type": "string"
                },
                "image_64": {
                  "default": None,
                  "format": "uri",
                  "minLength": 1,
                  "nullable": True,
                  "title": "Image 64",
                  "type": "string"
                }
              },
              "title": "Icons1",
              "type": "object"
            },
            "inviter": {
              "default": None,
              "description": "User ID of the user who invited others to the channel, if this message is related to an invitation.",
              "nullable": True,
              "pattern": "^[UW][A-Z0-9]{2,}$",
              "title": "Inviter",
              "type": "string"
            },
            "is_delayed_message": {
              "default": None,
              "description": "Indicates if this message was posted via a scheduled send.",
              "nullable": True,
              "title": "Is Delayed Message",
              "type": "boolean"
            },
            "is_intro": {
              "default": None,
              "description": "Indicates if this is an introductory message for a newly created channel or DM.",
              "nullable": True,
              "title": "Is Intro",
              "type": "boolean"
            },
            "is_starred": {
              "default": None,
              "description": "Indicates if the message has been starred by the authenticated user.",
              "nullable": True,
              "title": "Is Starred",
              "type": "boolean"
            },
            "last_read": {
              "default": None,
              "description": "Timestamp of when the channel was last read by the user.",
              "nullable": True,
              "pattern": "^\\d{10}\\.\\d{6}$",
              "title": "Last Read",
              "type": "string"
            },
            "latest_reply": {
              "default": None,
              "description": "Timestamp of the latest reply in the thread, if this message is a parent message.",
              "nullable": True,
              "pattern": "^\\d{10}\\.\\d{6}$",
              "title": "Latest Reply",
              "type": "string"
            },
            "metadata": {
              "additionalProperties": False,
              "default": None,
              "description": "Message metadata object as defined by Slack.\n\nContains an application-defined event_type and an arbitrary event_payload.",
              "nullable": True,
              "properties": {
                "event_payload": {
                  "additionalProperties": True,
                  "default": None,
                  "description": "Arbitrary structured payload defined by the app for the given event_type.",
                  "nullable": True,
                  "title": "Event Payload",
                  "type": "object"
                },
                "event_type": {
                  "description": "Application-defined type string describing the metadata event.",
                  "title": "Event Type",
                  "type": "string"
                }
              },
              "required": [
                "event_type"
              ],
              "title": "MessageMetadata",
              "type": "object"
            },
            "name": {
              "default": None,
              "description": "Name of the entity that posted the message (e.g., bot name), if applicable.",
              "nullable": True,
              "title": "Name",
              "type": "string"
            },
            "old_name": {
              "default": None,
              "description": "Previous name of a channel, if this message relates to a channel rename.",
              "nullable": True,
              "title": "Old Name",
              "type": "string"
            },
            "parent_user_id": {
              "default": None,
              "description": "User ID of the parent message's author, if this message is part of a thread.",
              "nullable": True,
              "pattern": "^[UW][A-Z0-9]{2,}$",
              "title": "Parent User Id",
              "type": "string"
            },
            "permalink": {
              "default": None,
              "description": "A permanent link to this specific message.",
              "format": "uri",
              "minLength": 1,
              "nullable": True,
              "title": "Permalink",
              "type": "string"
            },
            "pinned_to": {
              "default": None,
              "description": "List of channels or conversations this message is pinned to.",
              "items": {
                "pattern": "^[CGD][A-Z0-9]{8,}$",
                "properties": {},
                "title": "PinnedToItem",
                "type": "string"
              },
              "nullable": True,
              "title": "Pinned To",
              "type": "array"
            },
            "purpose": {
              "default": None,
              "description": "The purpose of the channel, if this message is a channel purpose update.",
              "nullable": True,
              "title": "Purpose",
              "type": "string"
            },
            "reactions": {
              "default": None,
              "description": "A list of reactions (emojis) added to this message.",
              "items": {
                "additionalProperties": True,
                "properties": {
                  "count": {
                    "title": "Count",
                    "type": "integer"
                  },
                  "name": {
                    "title": "Name",
                    "type": "string"
                  },
                  "users": {
                    "items": {
                      "pattern": "^[UW][A-Z0-9]{2,}$",
                      "properties": {},
                      "title": "User",
                      "type": "string"
                    },
                    "title": "Users",
                    "type": "array"
                  }
                },
                "required": [
                  "count",
                  "name",
                  "users"
                ],
                "title": "Reaction",
                "type": "object"
              },
              "nullable": True,
              "title": "Reactions",
              "type": "array"
            },
            "reply_count": {
              "default": None,
              "description": "Number of replies in the thread, if this message is a parent message.",
              "nullable": True,
              "title": "Reply Count",
              "type": "integer"
            },
            "reply_users": {
              "default": None,
              "description": "List of user IDs who have replied to this message thread.",
              "items": {
                "pattern": "^[UW][A-Z0-9]{2,}$",
                "properties": {},
                "title": "ReplyUser",
                "type": "string"
              },
              "minItems": 1,
              "nullable": True,
              "title": "Reply Users",
              "type": "array"
            },
            "reply_users_count": {
              "default": None,
              "description": "Total number of unique users who have replied to this message thread.",
              "nullable": True,
              "title": "Reply Users Count",
              "type": "integer"
            },
            "source_team": {
              "default": None,
              "description": "ID of the team from which the message originated, especially in shared channels.",
              "nullable": True,
              "pattern": "^[TE][A-Z0-9]{8,}$",
              "title": "Source Team",
              "type": "string"
            },
            "subscribed": {
              "default": None,
              "description": "Indicates if the authenticated user is subscribed to the thread.",
              "nullable": True,
              "title": "Subscribed",
              "type": "boolean"
            },
            "subtype": {
              "default": None,
              "description": "The type of message, indicating variations like 'channel_join', 'file_share', etc. Standard messages do not have a subtype.",
              "nullable": True,
              "title": "Subtype",
              "type": "string"
            },
            "team": {
              "default": None,
              "description": "ID of the team to which this message belongs.",
              "nullable": True,
              "pattern": "^[TE][A-Z0-9]{8,}$",
              "title": "Team",
              "type": "string"
            },
            "text": {
              "default": None,
              "description": "The message text. If blocks are used, this may be a fallback string for notifications or a rendered representation of the block content.",
              "nullable": True,
              "title": "Text",
              "type": "string"
            },
            "thread_ts": {
              "default": None,
              "description": "Timestamp of the parent message, if this message is part of a thread. This value matches the `ts` of the parent message.",
              "nullable": True,
              "pattern": "^\\d{10}\\.\\d{6}$",
              "title": "Thread Ts",
              "type": "string"
            },
            "topic": {
              "default": None,
              "description": "The topic of the channel, if this message is a channel topic update.",
              "nullable": True,
              "title": "Topic",
              "type": "string"
            },
            "ts": {
              "description": "Timestamp of when the message was posted. Unique identifier for the message.",
              "pattern": "^\\d{10}\\.\\d{6}$",
              "title": "Ts",
              "type": "string"
            },
            "type": {
              "description": "Message type. For standard messages this is \"message\".",
              "title": "Type",
              "type": "string"
            },
            "unread_count": {
              "default": None,
              "description": "Number of unread messages in the channel for the user.",
              "nullable": True,
              "title": "Unread Count",
              "type": "integer"
            },
            "upload": {
              "default": None,
              "description": "Indicates if the message is related to a file upload.",
              "nullable": True,
              "title": "Upload",
              "type": "boolean"
            },
            "user": {
              "default": None,
              "description": "User ID attributed to the message (often the bot user ID when posted by an app).",
              "nullable": True,
              "pattern": "^[UW][A-Z0-9]{2,}$",
              "title": "User",
              "type": "string"
            },
            "user_profile": {
              "additionalProperties": False,
              "default": None,
              "description": "Profile information of the user who posted the message, if available.",
              "nullable": True,
              "properties": {
                "avatar_hash": {
                  "title": "Avatar Hash",
                  "type": "string"
                },
                "display_name": {
                  "title": "Display Name",
                  "type": "string"
                },
                "display_name_normalized": {
                  "default": None,
                  "nullable": True,
                  "title": "Display Name Normalized",
                  "type": "string"
                },
                "first_name": {
                  "title": "First Name",
                  "type": "string"
                },
                "image_72": {
                  "format": "uri",
                  "minLength": 1,
                  "title": "Image 72",
                  "type": "string"
                },
                "is_restricted": {
                  "title": "Is Restricted",
                  "type": "boolean"
                },
                "is_ultra_restricted": {
                  "title": "Is Ultra Restricted",
                  "type": "boolean"
                },
                "name": {
                  "title": "Name",
                  "type": "string"
                },
                "real_name": {
                  "title": "Real Name",
                  "type": "string"
                },
                "real_name_normalized": {
                  "default": None,
                  "nullable": True,
                  "title": "Real Name Normalized",
                  "type": "string"
                },
                "team": {
                  "pattern": "^[TE][A-Z0-9]{8,}$",
                  "title": "Team",
                  "type": "string"
                }
              },
              "required": [
                "avatar_hash",
                "display_name",
                "first_name",
                "image_72",
                "is_restricted",
                "is_ultra_restricted",
                "name",
                "real_name",
                "team"
              ],
              "title": "UserProfile",
              "type": "object"
            },
            "user_team": {
              "default": None,
              "description": "ID of the team to which the posting user belongs.",
              "nullable": True,
              "pattern": "^[TE][A-Z0-9]{8,}$",
              "title": "User Team",
              "type": "string"
            },
            "username": {
              "default": None,
              "description": "Display name associated with the message author when applicable (for example, bot messages).",
              "nullable": True,
              "title": "Username",
              "type": "string"
            }
          },
          "required": [
            "ts",
            "type"
          ],
          "title": "Message",
          "type": "object"
        },
        "message_context": {
          "additionalProperties": False,
          "default": None,
          "description": "An individual instance of the message that was sent (Slack Functions).",
          "nullable": True,
          "properties": {
            "channel_id": {
              "default": None,
              "nullable": True,
              "title": "Channel Id",
              "type": "string"
            },
            "message_ts": {
              "title": "Message Ts",
              "type": "string"
            }
          },
          "required": [
            "message_ts"
          ],
          "title": "MessageContext",
          "type": "object"
        },
        "message_link": {
          "default": None,
          "description": "Permalink URL of the message that was sent (Slack Functions).",
          "format": "uri",
          "minLength": 1,
          "nullable": True,
          "title": "Message Link",
          "type": "string"
        },
        "message_ts": {
          "default": None,
          "description": "Channel-specific unique identifier (timestamp) for the sent message (Slack Functions).",
          "nullable": True,
          "title": "Message Ts",
          "type": "string"
        },
        "needed": {
          "default": None,
          "description": "The OAuth scope required to access the method, returned when the provided token lacks sufficient scope.",
          "nullable": True,
          "title": "Needed",
          "type": "string"
        },
        "ok": {
          "description": "Indicates whether the request was successful.",
          "title": "Ok",
          "type": "boolean"
        },
        "provided": {
          "default": None,
          "description": "The OAuth scopes associated with the provided token when an authorization error occurs.",
          "nullable": True,
          "title": "Provided",
          "type": "string"
        },
        "response_metadata": {
          "additionalProperties": False,
          "default": None,
          "description": "Additional metadata about the response, including warnings and human-readable messages.",
          "nullable": True,
          "properties": {
            "messages": {
              "default": None,
              "description": "Array of human-readable messages explaining warnings or notices.",
              "items": {
                "properties": {},
                "type": "string"
              },
              "nullable": True,
              "title": "Messages",
              "type": "array"
            },
            "warnings": {
              "default": None,
              "description": "Array of warning codes related to the request or response.",
              "items": {
                "properties": {},
                "type": "string"
              },
              "nullable": True,
              "title": "Warnings",
              "type": "array"
            }
          },
          "title": "ResponseMetadata",
          "type": "object"
        },
        "ts": {
          "default": None,
          "description": "Timestamp ID of the posted message in the channel (e.g., \"1503435956.000247\"). Present when ok is true.",
          "nullable": True,
          "title": "Ts",
          "type": "string"
        },
        "warning": {
          "default": None,
          "description": "Optional top-level warning string.",
          "nullable": True,
          "title": "Warning",
          "type": "string"
        },
        "warnings": {
          "default": None,
          "description": "Array of machine-readable warning codes related to the request (e.g., 'message_truncated', 'missing_charset', 'superfluous_charset').",
          "items": {
            "properties": {},
            "type": "string"
          },
          "nullable": True,
          "title": "Warnings",
          "type": "array"
        }
      },
      "required": [
        "ok"
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
  "title": "SendMessageResponseWrapper",
  "type": "object"
}

slack_search_messages_output_schema = {
  "properties": {
    "data": {
      "additionalProperties": False,
      "description": "Data from the action execution",
      "properties": {
        "bots": {
          "additionalProperties": True,
          "default": None,
          "nullable": True,
          "title": "Bots",
          "type": "object"
        },
        "error": {
          "default": None,
          "nullable": True,
          "title": "Error",
          "type": "string"
        },
        "messages": {
          "additionalProperties": False,
          "default": None,
          "nullable": True,
          "properties": {
            "matches": {
              "items": {
                "properties": {
                  "attachments": {
                    "default": None,
                    "items": {
                      "properties": {
                        "actions": {
                          "default": None,
                          "items": {
                            "properties": {
                              "id": {
                                "default": None,
                                "nullable": True,
                                "title": "Id",
                                "type": "string"
                              },
                              "name": {
                                "default": None,
                                "nullable": True,
                                "title": "Name",
                                "type": "string"
                              },
                              "style": {
                                "default": None,
                                "nullable": True,
                                "title": "Style",
                                "type": "string"
                              },
                              "text": {
                                "default": None,
                                "nullable": True,
                                "title": "Text",
                                "type": "string"
                              },
                              "type": {
                                "default": None,
                                "nullable": True,
                                "title": "Type",
                                "type": "string"
                              },
                              "value": {
                                "default": None,
                                "nullable": True,
                                "title": "Value",
                                "type": "string"
                              }
                            },
                            "title": "AttachmentAction",
                            "type": "object"
                          },
                          "nullable": True,
                          "title": "Actions",
                          "type": "array"
                        },
                        "callback_id": {
                          "default": None,
                          "nullable": True,
                          "title": "Callback Id",
                          "type": "string"
                        },
                        "color": {
                          "default": None,
                          "nullable": True,
                          "title": "Color",
                          "type": "string"
                        },
                        "fields": {
                          "default": None,
                          "items": {
                            "properties": {
                              "short": {
                                "default": None,
                                "nullable": True,
                                "title": "Short",
                                "type": "boolean"
                              },
                              "title": {
                                "default": None,
                                "nullable": True,
                                "title": "Title",
                                "type": "string"
                              },
                              "value": {
                                "default": None,
                                "nullable": True,
                                "title": "Value",
                                "type": "string"
                              }
                            },
                            "title": "AttachmentField",
                            "type": "object"
                          },
                          "nullable": True,
                          "title": "Fields",
                          "type": "array"
                        },
                        "footer": {
                          "default": None,
                          "nullable": True,
                          "title": "Footer",
                          "type": "string"
                        },
                        "footer_icon": {
                          "default": None,
                          "nullable": True,
                          "title": "Footer Icon",
                          "type": "string"
                        },
                        "id": {
                          "default": None,
                          "nullable": True,
                          "title": "Id",
                          "type": "integer"
                        },
                        "mrkdwn_in": {
                          "default": None,
                          "items": {
                            "properties": {},
                            "type": "string"
                          },
                          "nullable": True,
                          "title": "Mrkdwn In",
                          "type": "array"
                        },
                        "pretext": {
                          "default": None,
                          "nullable": True,
                          "title": "Pretext",
                          "type": "string"
                        },
                        "text": {
                          "default": None,
                          "nullable": True,
                          "title": "Text",
                          "type": "string"
                        },
                        "title": {
                          "default": None,
                          "nullable": True,
                          "title": "Title",
                          "type": "string"
                        },
                        "ts": {
                          "default": None,
                          "nullable": True,
                          "title": "Ts",
                          "type": "number"
                        }
                      },
                      "title": "Attachment",
                      "type": "object"
                    },
                    "nullable": True,
                    "title": "Attachments",
                    "type": "array"
                  },
                  "channel": {
                    "additionalProperties": False,
                    "properties": {
                      "id": {
                        "title": "Id",
                        "type": "string"
                      },
                      "is_channel": {
                        "default": None,
                        "nullable": True,
                        "title": "Is Channel",
                        "type": "boolean"
                      },
                      "is_ext_shared": {
                        "title": "Is Ext Shared",
                        "type": "boolean"
                      },
                      "is_group": {
                        "default": None,
                        "nullable": True,
                        "title": "Is Group",
                        "type": "boolean"
                      },
                      "is_im": {
                        "default": None,
                        "nullable": True,
                        "title": "Is Im",
                        "type": "boolean"
                      },
                      "is_mpim": {
                        "title": "Is Mpim",
                        "type": "boolean"
                      },
                      "is_org_shared": {
                        "title": "Is Org Shared",
                        "type": "boolean"
                      },
                      "is_pending_ext_shared": {
                        "title": "Is Pending Ext Shared",
                        "type": "boolean"
                      },
                      "is_private": {
                        "title": "Is Private",
                        "type": "boolean"
                      },
                      "is_shared": {
                        "title": "Is Shared",
                        "type": "boolean"
                      },
                      "name": {
                        "title": "Name",
                        "type": "string"
                      },
                      "name_normalized": {
                        "default": None,
                        "nullable": True,
                        "title": "Name Normalized",
                        "type": "string"
                      },
                      "pending_shared": {
                        "items": {
                          "properties": {},
                          "type": "string"
                        },
                        "title": "Pending Shared",
                        "type": "array"
                      },
                      "user": {
                        "default": None,
                        "nullable": True,
                        "title": "User",
                        "type": "string"
                      }
                    },
                    "required": [
                      "id",
                      "is_ext_shared",
                      "is_mpim",
                      "is_org_shared",
                      "is_pending_ext_shared",
                      "is_private",
                      "is_shared",
                      "name",
                      "pending_shared"
                    ],
                    "title": "Channel",
                    "type": "object"
                  },
                  "db_message": {
                    "additionalProperties": True,
                    "default": None,
                    "nullable": True,
                    "title": "Db Message",
                    "type": "object"
                  },
                  "files": {
                    "default": None,
                    "items": {
                      "description": "File attachment metadata as returned in search.messages matches.",
                      "properties": {
                        "file_access": {
                          "default": None,
                          "nullable": True,
                          "title": "File Access",
                          "type": "string"
                        },
                        "filetype": {
                          "default": None,
                          "nullable": True,
                          "title": "Filetype",
                          "type": "string"
                        },
                        "id": {
                          "default": None,
                          "nullable": True,
                          "title": "Id",
                          "type": "string"
                        },
                        "mimetype": {
                          "default": None,
                          "nullable": True,
                          "title": "Mimetype",
                          "type": "string"
                        },
                        "permalink": {
                          "default": None,
                          "nullable": True,
                          "title": "Permalink",
                          "type": "string"
                        },
                        "permalink_public": {
                          "default": None,
                          "nullable": True,
                          "title": "Permalink Public",
                          "type": "string"
                        },
                        "size": {
                          "default": None,
                          "nullable": True,
                          "title": "Size",
                          "type": "number"
                        },
                        "url_private": {
                          "default": None,
                          "nullable": True,
                          "title": "Url Private",
                          "type": "string"
                        },
                        "url_private_download": {
                          "default": None,
                          "nullable": True,
                          "title": "Url Private Download",
                          "type": "string"
                        }
                      },
                      "title": "FileAttachment",
                      "type": "object"
                    },
                    "nullable": True,
                    "title": "Files",
                    "type": "array"
                  },
                  "iid": {
                    "title": "Iid",
                    "type": "string"
                  },
                  "next": {
                    "additionalProperties": False,
                    "default": None,
                    "description": "Deprecated contextual message fields (previous/next) kept for compatibility.\nDocs note these were removed beginning Dec 3, 2020, but may appear in older payloads.",
                    "nullable": True,
                    "properties": {
                      "iid": {
                        "default": None,
                        "nullable": True,
                        "title": "Iid",
                        "type": "string"
                      },
                      "text": {
                        "default": None,
                        "nullable": True,
                        "title": "Text",
                        "type": "string"
                      },
                      "ts": {
                        "default": None,
                        "nullable": True,
                        "title": "Ts",
                        "type": "string"
                      },
                      "type": {
                        "default": None,
                        "nullable": True,
                        "title": "Type",
                        "type": "string"
                      },
                      "user": {
                        "default": None,
                        "nullable": True,
                        "title": "User",
                        "type": "string"
                      },
                      "username": {
                        "default": None,
                        "nullable": True,
                        "title": "Username",
                        "type": "string"
                      }
                    },
                    "title": "ContextMessage",
                    "type": "object"
                  },
                  "next_2": {
                    "additionalProperties": False,
                    "default": None,
                    "description": "Deprecated contextual message fields (previous/next) kept for compatibility.\nDocs note these were removed beginning Dec 3, 2020, but may appear in older payloads.",
                    "nullable": True,
                    "properties": {
                      "iid": {
                        "default": None,
                        "nullable": True,
                        "title": "Iid",
                        "type": "string"
                      },
                      "text": {
                        "default": None,
                        "nullable": True,
                        "title": "Text",
                        "type": "string"
                      },
                      "ts": {
                        "default": None,
                        "nullable": True,
                        "title": "Ts",
                        "type": "string"
                      },
                      "type": {
                        "default": None,
                        "nullable": True,
                        "title": "Type",
                        "type": "string"
                      },
                      "user": {
                        "default": None,
                        "nullable": True,
                        "title": "User",
                        "type": "string"
                      },
                      "username": {
                        "default": None,
                        "nullable": True,
                        "title": "Username",
                        "type": "string"
                      }
                    },
                    "title": "ContextMessage",
                    "type": "object"
                  },
                  "no_reactions": {
                    "default": None,
                    "nullable": True,
                    "title": "No Reactions",
                    "type": "boolean"
                  },
                  "permalink": {
                    "title": "Permalink",
                    "type": "string"
                  },
                  "previous": {
                    "additionalProperties": False,
                    "default": None,
                    "description": "Deprecated contextual message fields (previous/next) kept for compatibility.\nDocs note these were removed beginning Dec 3, 2020, but may appear in older payloads.",
                    "nullable": True,
                    "properties": {
                      "iid": {
                        "default": None,
                        "nullable": True,
                        "title": "Iid",
                        "type": "string"
                      },
                      "text": {
                        "default": None,
                        "nullable": True,
                        "title": "Text",
                        "type": "string"
                      },
                      "ts": {
                        "default": None,
                        "nullable": True,
                        "title": "Ts",
                        "type": "string"
                      },
                      "type": {
                        "default": None,
                        "nullable": True,
                        "title": "Type",
                        "type": "string"
                      },
                      "user": {
                        "default": None,
                        "nullable": True,
                        "title": "User",
                        "type": "string"
                      },
                      "username": {
                        "default": None,
                        "nullable": True,
                        "title": "Username",
                        "type": "string"
                      }
                    },
                    "title": "ContextMessage",
                    "type": "object"
                  },
                  "previous_2": {
                    "additionalProperties": False,
                    "default": None,
                    "description": "Deprecated contextual message fields (previous/next) kept for compatibility.\nDocs note these were removed beginning Dec 3, 2020, but may appear in older payloads.",
                    "nullable": True,
                    "properties": {
                      "iid": {
                        "default": None,
                        "nullable": True,
                        "title": "Iid",
                        "type": "string"
                      },
                      "text": {
                        "default": None,
                        "nullable": True,
                        "title": "Text",
                        "type": "string"
                      },
                      "ts": {
                        "default": None,
                        "nullable": True,
                        "title": "Ts",
                        "type": "string"
                      },
                      "type": {
                        "default": None,
                        "nullable": True,
                        "title": "Type",
                        "type": "string"
                      },
                      "user": {
                        "default": None,
                        "nullable": True,
                        "title": "User",
                        "type": "string"
                      },
                      "username": {
                        "default": None,
                        "nullable": True,
                        "title": "Username",
                        "type": "string"
                      }
                    },
                    "title": "ContextMessage",
                    "type": "object"
                  },
                  "score": {
                    "default": None,
                    "nullable": True,
                    "title": "Score",
                    "type": "number"
                  },
                  "team": {
                    "title": "Team",
                    "type": "string"
                  },
                  "text": {
                    "title": "Text",
                    "type": "string"
                  },
                  "ts": {
                    "title": "Ts",
                    "type": "string"
                  },
                  "type": {
                    "title": "Type",
                    "type": "string"
                  },
                  "user": {
                    "default": None,
                    "nullable": True,
                    "title": "User",
                    "type": "string"
                  },
                  "username": {
                    "default": None,
                    "nullable": True,
                    "title": "Username",
                    "type": "string"
                  }
                },
                "required": [
                  "channel",
                  "iid",
                  "permalink",
                  "team",
                  "text",
                  "ts",
                  "type"
                ],
                "title": "MessageMatch",
                "type": "object"
              },
              "title": "Matches",
              "type": "array"
            },
            "pagination": {
              "additionalProperties": False,
              "default": None,
              "nullable": True,
              "properties": {
                "first": {
                  "title": "First",
                  "type": "integer"
                },
                "last": {
                  "title": "Last",
                  "type": "integer"
                },
                "page": {
                  "title": "Page",
                  "type": "integer"
                },
                "page_count": {
                  "title": "Page Count",
                  "type": "integer"
                },
                "per_page": {
                  "title": "Per Page",
                  "type": "integer"
                },
                "total_count": {
                  "title": "Total Count",
                  "type": "integer"
                }
              },
              "required": [
                "first",
                "last",
                "page",
                "page_count",
                "per_page",
                "total_count"
              ],
              "title": "CursorPagination",
              "type": "object"
            },
            "paging": {
              "additionalProperties": False,
              "default": None,
              "nullable": True,
              "properties": {
                "count": {
                  "title": "Count",
                  "type": "integer"
                },
                "page": {
                  "title": "Page",
                  "type": "integer"
                },
                "pages": {
                  "title": "Pages",
                  "type": "integer"
                },
                "total": {
                  "title": "Total",
                  "type": "integer"
                }
              },
              "required": [
                "count",
                "page",
                "pages",
                "total"
              ],
              "title": "Paging",
              "type": "object"
            },
            "total": {
              "title": "Total",
              "type": "integer"
            }
          },
          "required": [
            "matches",
            "total"
          ],
          "title": "MessagesContainer",
          "type": "object"
        },
        "needed": {
          "default": None,
          "nullable": True,
          "title": "Needed",
          "type": "string"
        },
        "ok": {
          "title": "Ok",
          "type": "boolean"
        },
        "provided": {
          "default": None,
          "nullable": True,
          "title": "Provided",
          "type": "string"
        },
        "query": {
          "default": None,
          "nullable": True,
          "title": "Query",
          "type": "string"
        },
        "teams": {
          "additionalProperties": True,
          "default": None,
          "nullable": True,
          "title": "Teams",
          "type": "object"
        },
        "users": {
          "additionalProperties": True,
          "default": None,
          "nullable": True,
          "title": "Users",
          "type": "object"
        },
        "warnings": {
          "default": None,
          "items": {
            "properties": {},
            "type": "string"
          },
          "nullable": True,
          "title": "Warnings",
          "type": "array"
        }
      },
      "required": [
        "ok"
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
  "title": "SearchMessagesResponseWrapper",
  "type": "object"
}