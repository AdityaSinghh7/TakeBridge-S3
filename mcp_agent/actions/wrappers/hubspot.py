"""HubSpot action wrappers.

Handles parameter mapping and MCP tool invocation for HubSpot.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from mcp_agent.types import ToolInvocationResult

from ._common import _clean_payload, _invoke_mcp_tool, ensure_authorized

if TYPE_CHECKING:
    from mcp_agent.core.context import AgentContext


def hubspot_update_deals(
    context: "AgentContext",
    inputs: list[dict[str, Any]],
) -> ToolInvocationResult:
    """
    Description:
        Updates multiple HubSpot deals in a single batch operation.
    Args:
        inputs: Add the deal updates you want to perform in this batch. Each item should include the deal's ID and the fields you want to change. For each item: id is the unique deal ID (copy it from the deal URL or a list/search), and properties are the fields + new values to update (for example amount, stage, or close date). Only include properties you want to change.
    """
    provider = "hubspot"
    tool_name = "HUBSPOT_UPDATE_DEALS"
    ensure_authorized(context, provider)
    payload = _clean_payload({"inputs": inputs})
    return _invoke_mcp_tool(context, provider, tool_name, payload)


hubspot_update_deals.__tb_output_schema__ = {
    "properties": {
        "data": {
            "additionalProperties": False,
            "description": "Data from the action execution",
            "properties": {
                "completedAt": {
                    "description": "Timestamp when the batch processing was completed, in ISO 8601 format (date-time).",
                    "title": "Completed At",
                    "type": "string",
                },
                "errors": {
                    "default": None,
                    "description": (
                        "Array of error objects for failed operations. Present when one or more batch "
                        "operations fail (207 Multi-Status response)."
                    ),
                    "items": {
                        "description": "Error information for a failed batch operation.",
                        "properties": {
                            "category": {
                                "description": "High-level error classification (e.g., VALIDATION_ERROR, OBJECT_NOT_FOUND).",
                                "title": "Category",
                                "type": "string",
                            },
                            "context": {
                                "additionalProperties": {
                                    "items": {"type": "string"},
                                    "type": "array",
                                },
                                "description": "Additional contextual data about the error.",
                                "title": "Context",
                                "type": "object",
                            },
                            "errors": {
                                "description": "Array of detailed error information.",
                                "items": {
                                    "description": "Detailed error information.",
                                    "properties": {
                                        "code": {
                                            "default": None,
                                            "description": "The status code associated with the error detail.",
                                            "nullable": True,
                                            "title": "Code",
                                            "type": "string",
                                        },
                                        "context": {
                                            "additionalProperties": {
                                                "items": {"type": "string"},
                                                "type": "array",
                                            },
                                            "default": None,
                                            "description": "Context about the error condition.",
                                            "nullable": True,
                                            "title": "Context",
                                            "type": "object",
                                        },
                                        "in": {
                                            "default": None,
                                            "description": "The name of the field or parameter in which the error was found.",
                                            "nullable": True,
                                            "title": "In",
                                            "type": "string",
                                        },
                                        "message": {
                                            "description": (
                                                "Human-readable message describing the error along with remediation "
                                                "steps where appropriate."
                                            ),
                                            "title": "Message",
                                            "type": "string",
                                        },
                                        "subCategory": {
                                            "default": None,
                                            "description": (
                                                "A specific category that contains more specific detail about the error."
                                            ),
                                            "nullable": True,
                                            "title": "Sub Category",
                                            "type": "string",
                                        },
                                    },
                                    "required": ["message"],
                                    "title": "ErrorDetail",
                                    "type": "object",
                                },
                                "title": "Errors",
                                "type": "array",
                            },
                            "id": {
                                "default": None,
                                "description": "Optional error identifier.",
                                "nullable": True,
                                "title": "Id",
                                "type": "string",
                            },
                            "links": {
                                "additionalProperties": {"type": "string"},
                                "description": "Related resource references.",
                                "title": "Links",
                                "type": "object",
                            },
                            "message": {
                                "description": "Human-readable error message with details about the error.",
                                "title": "Message",
                                "type": "string",
                            },
                            "status": {
                                "description": "HTTP status code for this error.",
                                "title": "Status",
                                "type": "string",
                            },
                            "subCategory": {
                                "default": None,
                                "description": (
                                    "Optional error subcategory with additional classification details."
                                ),
                                "nullable": True,
                                "title": "Sub Category",
                            },
                        },
                        "required": [
                            "status",
                            "category",
                            "message",
                            "errors",
                            "context",
                            "links",
                        ],
                        "title": "BatchError",
                        "type": "object",
                    },
                    "nullable": True,
                    "title": "Errors",
                    "type": "array",
                },
                "links": {
                    "additionalProperties": {"type": "string"},
                    "default": None,
                    "description": "Related documentation or resource URLs.",
                    "nullable": True,
                    "title": "Links",
                    "type": "object",
                },
                "numErrors": {
                    "default": None,
                    "description": (
                        "Count of errors encountered during the batch operation. Present when there are errors."
                    ),
                    "nullable": True,
                    "title": "Num Errors",
                    "type": "integer",
                },
                "requestedAt": {
                    "default": None,
                    "description": "Timestamp when the batch request was made, in ISO 8601 format (date-time).",
                    "nullable": True,
                    "title": "Requested At",
                    "type": "string",
                },
                "results": {
                    "description": "Array of successfully updated deal objects.",
                    "items": {
                        "description": "Represents a deal object returned in the batch response.",
                        "properties": {
                            "archived": {
                                "default": None,
                                "description": "Boolean flag indicating whether the deal is archived.",
                                "nullable": True,
                                "title": "Archived",
                                "type": "boolean",
                            },
                            "archivedAt": {
                                "default": None,
                                "description": "Timestamp recording when the deal was archived, in ISO 8601 format (date-time).",
                                "nullable": True,
                                "title": "Archived At",
                                "type": "string",
                            },
                            "createdAt": {
                                "description": "Timestamp indicating when the deal was created, in ISO 8601 format (date-time).",
                                "title": "Created At",
                                "type": "string",
                            },
                            "id": {
                                "description": "Unique identifier for the deal object.",
                                "title": "Id",
                                "type": "string",
                            },
                            "objectWriteTraceId": {
                                "default": None,
                                "description": "Trace identifier for tracking the write operation.",
                                "nullable": True,
                                "title": "Object Write Trace Id",
                                "type": "string",
                            },
                            "properties": {
                                "additionalProperties": {"type": "string"},
                                "description": "Key-value pairs containing deal-specific property values.",
                                "title": "Properties",
                                "type": "object",
                            },
                            "propertiesWithHistory": {
                                "additionalProperties": {
                                    "items": {
                                        "description": "Historical record of a property value change.",
                                        "properties": {
                                            "sourceId": {
                                                "anyOf": [
                                                    {"type": "string"},
                                                    {"type": "null"},
                                                ],
                                                "default": None,
                                                "description": "Identifier of the source that made the change.",
                                                "title": "Sourceid",
                                            },
                                            "sourceLabel": {
                                                "anyOf": [
                                                    {"type": "string"},
                                                    {"type": "null"},
                                                ],
                                                "default": None,
                                                "description": "Human-readable label for the source.",
                                                "title": "Sourcelabel",
                                            },
                                            "sourceType": {
                                                "description": "The source type of the property change.",
                                                "title": "Sourcetype",
                                                "type": "string",
                                            },
                                            "timestamp": {
                                                "description": "Timestamp when this value was set, in ISO 8601 format (date-time).",
                                                "title": "Timestamp",
                                                "type": "string",
                                            },
                                            "updatedByUserId": {
                                                "anyOf": [
                                                    {"type": "integer"},
                                                    {"type": "null"},
                                                ],
                                                "default": None,
                                                "description": "User ID of the person who made the update.",
                                                "title": "Updatedbyuserid",
                                            },
                                            "value": {
                                                "description": "The property value at this point in history.",
                                                "title": "Value",
                                                "type": "string",
                                            },
                                        },
                                        "required": ["value", "timestamp", "sourceType"],
                                        "title": "PropertyHistoryItem",
                                        "type": "object",
                                    },
                                    "type": "array",
                                },
                                "default": None,
                                "description": "Historical tracking of property value changes over time.",
                                "nullable": True,
                                "title": "Properties With History",
                                "type": "object",
                            },
                            "updatedAt": {
                                "description": "Timestamp indicating when the deal was last modified, in ISO 8601 format (date-time).",
                                "title": "Updated At",
                                "type": "string",
                            },
                        },
                        "required": ["id", "properties", "createdAt", "updatedAt"],
                        "title": "DealObject",
                        "type": "object",
                    },
                    "title": "Results",
                    "type": "array",
                },
                "startedAt": {
                    "description": "Timestamp when the batch processing began, in ISO 8601 format (date-time).",
                    "title": "Started At",
                    "type": "string",
                },
                "status": {
                    "description": "The status of the batch operation. Must be one of: PENDING, PROCESSING, CANCELED, COMPLETE.",
                    "title": "Status",
                    "type": "string",
                },
            },
            "required": ["status", "results", "startedAt", "completedAt"],
            "title": "Data",
            "type": "object",
        },
        "error": {
            "default": None,
            "description": "Error if any occurred during the execution of the action",
            "nullable": True,
            "title": "Error",
            "type": "string",
        },
        "successful": {
            "description": "Whether or not the action execution was successful or not",
            "title": "Successful",
            "type": "boolean",
        },
    },
    "required": ["data", "successful"],
    "title": "UpdateBatchOfDealsResponseWrapper",
    "type": "object",
}


def hubspot_update_contacts(
    context: "AgentContext",
    inputs: list[dict[str, Any]],
) -> ToolInvocationResult:
    """
    Description:
        Updates multiple HubSpot contacts in a single batch operation.
    Args:
        inputs: A list of contact updates to perform in one request. For each item, provide the contact ID (VID) and
            the fields you want to change. Use the HubSpot internal property names for the properties object. Internal
            property names: address, annualrevenue, associatedcompanyid, associatedcompanylastupdated, city, closedate,
            company, company_size, country, createdate, currentlyinworkflow, date_of_birth, days_to_close, degree,
            email, engagements_last_meeting_booked, engagements_last_meeting_booked_campaign,
            engagements_last_meeting_booked_medium, engagements_last_meeting_booked_source, fax, field_of_study,
            first_conversion_date, first_conversion_event_name, first_deal_created_date, firstname, followercount,
            gender, graduation_date, hs_additional_emails, hs_all_accessible_team_ids,
            hs_all_assigned_business_unit_ids, hs_all_contact_vids, hs_all_owner_ids, hs_all_team_ids,
            hs_analytics_average_page_views, hs_analytics_first_referrer, hs_analytics_first_timestamp,
            hs_analytics_first_touch_converting_campaign, hs_analytics_first_url, hs_analytics_first_visit_timestamp,
            hs_analytics_last_referrer, hs_analytics_last_timestamp, hs_analytics_last_touch_converting_campaign,
            hs_analytics_last_url, hs_analytics_last_visit_timestamp, hs_analytics_num_event_completions,
            hs_analytics_num_page_views, hs_analytics_num_visits, hs_analytics_revenue, hs_analytics_source,
            hs_analytics_source_data_1, hs_analytics_source_data_2, hs_lead_status, hubspot_owner_assigneddate,
            hubspot_owner_id, hubspot_team_id, hubspotscore, industry, ip_city, ip_country, ip_country_code, ip_latlon,
            ip_state, ip_state_code, ip_zipcode, job_function, jobtitle, kloutscoregeneral, lastmodifieddate, lastname,
            lifecyclestage, linkedinbio, linkedinconnections, marital_status, message, military_status, mobilephone,
            notes_last_contacted, notes_last_updated, notes_next_activity_date, num_associated_deals,
            num_contacted_notes, num_conversion_events, num_notes, num_unique_conversion_events, numemployees,
            owneremail, ownername, phone, photo, recent_conversion_date, recent_conversion_event_name,
            recent_deal_amount, recent_deal_close_date, relationship_status, salutation, school, seniority, start_date,
            state, surveymonkeyeventlastupdated, total_revenue, twitterbio, twitterhandle, twitterprofilephoto,
            webinareventlastupdated, website, work_email, zip.
    """
    provider = "hubspot"
    tool_name = "HUBSPOT_UPDATE_CONTACTS"
    ensure_authorized(context, provider)
    payload = _clean_payload({"inputs": inputs})
    return _invoke_mcp_tool(context, provider, tool_name, payload)


hubspot_update_contacts.__tb_output_schema__ = {
    "properties": {
        "data": {
            "additionalProperties": False,
            "description": "Data from the action execution",
            "properties": {
                "completedAt": {
                    "description": "Timestamp when the batch processing was completed, in ISO 8601 format",
                    "title": "Completed At",
                    "type": "string",
                },
                "errors": {
                    "default": None,
                    "description": (
                        "Array of error objects for failed operations. Present in 207 Multi-Status responses when one "
                        "or more batch operations fail"
                    ),
                    "items": {
                        "description": "Error object for a contact that failed to update.",
                        "properties": {
                            "category": {
                                "description": "The main category or classification of the error",
                                "title": "Category",
                                "type": "string",
                            },
                            "context": {
                                "additionalProperties": {
                                    "items": {"type": "string"},
                                    "type": "array",
                                },
                                "description": (
                                    "Contextual data mapping strings to string arrays for additional error details"
                                ),
                                "title": "Context",
                                "type": "object",
                            },
                            "errors": {
                                "description": "Collection of detailed error information objects",
                                "items": {
                                    "description": "Detailed error information for validation or processing failures.",
                                    "properties": {
                                        "code": {
                                            "default": None,
                                            "description": "The status code associated with the error detail",
                                            "nullable": True,
                                            "title": "Code",
                                            "type": "string",
                                        },
                                        "context": {
                                            "additionalProperties": {
                                                "items": {"type": "string"},
                                                "type": "array",
                                            },
                                            "default": None,
                                            "description": (
                                                "Context about the error condition, mapping strings to arrays of strings"
                                            ),
                                            "nullable": True,
                                            "title": "Context",
                                            "type": "object",
                                        },
                                        "in": {
                                            "default": None,
                                            "description": "The name of the field or parameter in which the error was found",
                                            "nullable": True,
                                            "title": "In",
                                            "type": "string",
                                        },
                                        "message": {
                                            "description": (
                                                "A human readable message describing the error along with remediation "
                                                "steps where appropriate"
                                            ),
                                            "title": "Message",
                                            "type": "string",
                                        },
                                        "subCategory": {
                                            "default": None,
                                            "description": (
                                                "A specific category that contains more specific detail about the error"
                                            ),
                                            "nullable": True,
                                            "title": "Sub Category",
                                            "type": "string",
                                        },
                                    },
                                    "required": ["message"],
                                    "title": "ErrorDetail",
                                    "type": "object",
                                },
                                "title": "Errors",
                                "type": "array",
                            },
                            "id": {
                                "default": None,
                                "description": "Unique identifier for the error instance",
                                "nullable": True,
                                "title": "Id",
                                "type": "string",
                            },
                            "links": {
                                "additionalProperties": {"type": "string"},
                                "description": "Navigation links relevant to the error response as key-value pairs",
                                "title": "Links",
                                "type": "object",
                            },
                            "message": {
                                "description": (
                                    "A human-readable string describing the error and possible remediation steps"
                                ),
                                "title": "Message",
                                "type": "string",
                            },
                            "status": {
                                "description": "HTTP status code associated with the error",
                                "title": "Status",
                                "type": "string",
                            },
                            "subCategory": {
                                "default": None,
                                "description": "Subcategory providing additional classification detail about the error",
                                "nullable": True,
                                "title": "Sub Category",
                            },
                        },
                        "required": [
                            "status",
                            "category",
                            "message",
                            "errors",
                            "context",
                            "links",
                        ],
                        "title": "BatchError",
                        "type": "object",
                    },
                    "nullable": True,
                    "title": "Errors",
                    "type": "array",
                },
                "links": {
                    "additionalProperties": {"type": "string"},
                    "default": None,
                    "description": "Dictionary containing related resource links as key-value pairs",
                    "nullable": True,
                    "title": "Links",
                    "type": "object",
                },
                "numErrors": {
                    "default": None,
                    "description": (
                        "Count of errors encountered during batch processing. Present in 207 Multi-Status responses"
                    ),
                    "nullable": True,
                    "title": "Num Errors",
                    "type": "integer",
                },
                "requestedAt": {
                    "default": None,
                    "description": "Timestamp when the batch request was initially submitted, in ISO 8601 format",
                    "nullable": True,
                    "title": "Requested At",
                    "type": "string",
                },
                "results": {
                    "description": "Array of successfully updated contact objects",
                    "items": {
                        "description": "Successfully updated contact record.",
                        "properties": {
                            "archived": {
                                "description": "Flag indicating whether the contact is archived",
                                "title": "Archived",
                                "type": "boolean",
                            },
                            "archivedAt": {
                                "default": None,
                                "description": "Timestamp when the contact was archived, in ISO 8601 format",
                                "nullable": True,
                                "title": "Archived At",
                                "type": "string",
                            },
                            "associations": {
                                "additionalProperties": {
                                    "description": "Association results for a specific object type.",
                                    "properties": {
                                        "paging": {
                                            "anyOf": [
                                                {
                                                    "description": "Pagination information for associations.",
                                                    "properties": {
                                                        "next": {
                                                            "anyOf": [
                                                                {
                                                                    "description": (
                                                                        "Pagination information for retrieving "
                                                                        "next page of associations."
                                                                    ),
                                                                    "properties": {
                                                                        "after": {
                                                                            "description": (
                                                                                "Cursor value for retrieving the "
                                                                                "next page of associations."
                                                                            ),
                                                                            "title": "After",
                                                                            "type": "string",
                                                                        },
                                                                        "link": {
                                                                            "anyOf": [
                                                                                {"type": "string"},
                                                                                {"type": "null"},
                                                                            ],
                                                                            "default": None,
                                                                            "description": "URL for the next paginated request.",
                                                                            "title": "Link",
                                                                        },
                                                                    },
                                                                    "required": ["after"],
                                                                    "title": "AssociationPagingNext",
                                                                    "type": "object",
                                                                },
                                                                {"type": "null"},
                                                            ],
                                                            "default": None,
                                                            "description": "Next page information.",
                                                        }
                                                    },
                                                    "title": "AssociationPaging",
                                                    "type": "object",
                                                },
                                                {"type": "null"},
                                            ],
                                            "default": None,
                                            "description": (
                                                "Pagination information for associations (when more than 100 "
                                                "associations exist)."
                                            ),
                                        },
                                        "results": {
                                            "description": "Array of associated records.",
                                            "items": {
                                                "description": "An associated object record.",
                                                "properties": {
                                                    "id": {
                                                        "description": "The unique ID of the associated object.",
                                                        "title": "Id",
                                                        "type": "string",
                                                    },
                                                    "type": {
                                                        "description": "The type of the association.",
                                                        "title": "Type",
                                                        "type": "string",
                                                    },
                                                },
                                                "required": ["id", "type"],
                                                "title": "AssociatedObject",
                                                "type": "object",
                                            },
                                            "title": "Results",
                                            "type": "array",
                                        },
                                    },
                                    "required": ["results"],
                                    "title": "AssociationResults",
                                    "type": "object",
                                },
                                "default": None,
                                "description": (
                                    "Related objects associated with the contact, maps object type to "
                                    "CollectionResponseAssociatedId"
                                ),
                                "nullable": True,
                                "title": "Associations",
                                "type": "object",
                            },
                            "createdAt": {
                                "description": "Timestamp when the contact was created, in ISO 8601 format",
                                "title": "Created At",
                                "type": "string",
                            },
                            "id": {
                                "description": "Unique identifier for the contact object",
                                "title": "Id",
                                "type": "string",
                            },
                            "objectWriteTraceId": {
                                "default": None,
                                "description": "Trace identifier for the write operation",
                                "nullable": True,
                                "title": "Object Write Trace Id",
                                "type": "string",
                            },
                            "properties": {
                                "additionalProperties": {
                                    "anyOf": [
                                        {"type": "string"},
                                        {"type": "null"},
                                    ]
                                },
                                "description": (
                                    "Custom properties stored as key-value pairs where values are strings or null"
                                ),
                                "title": "Properties",
                                "type": "object",
                            },
                            "propertiesWithHistory": {
                                "additionalProperties": {
                                    "items": {
                                        "description": "Historical value entry for a contact property.",
                                        "properties": {
                                            "sourceId": {
                                                "anyOf": [
                                                    {"type": "string"},
                                                    {"type": "null"},
                                                ],
                                                "default": None,
                                                "description": "Unique property identifier.",
                                                "title": "Sourceid",
                                            },
                                            "sourceLabel": {
                                                "anyOf": [
                                                    {"type": "string"},
                                                    {"type": "null"},
                                                ],
                                                "default": None,
                                                "description": "Human-readable label.",
                                                "title": "Sourcelabel",
                                            },
                                            "sourceType": {
                                                "description": "The property type.",
                                                "title": "Sourcetype",
                                                "type": "string",
                                            },
                                            "timestamp": {
                                                "description": "When the property was updated.",
                                                "title": "Timestamp",
                                                "type": "string",
                                            },
                                            "updatedByUserId": {
                                                "anyOf": [
                                                    {"type": "integer"},
                                                    {"type": "null"},
                                                ],
                                                "default": None,
                                                "description": "ID of user who updated it.",
                                                "title": "Updatedbyuserid",
                                            },
                                            "value": {
                                                "description": "The property value.",
                                                "title": "Value",
                                                "type": "string",
                                            },
                                        },
                                        "required": [
                                            "sourceType",
                                            "timestamp",
                                            "value",
                                        ],
                                        "title": "PropertyHistoryItem",
                                        "type": "object",
                                    },
                                    "type": "array",
                                },
                                "default": None,
                                "description": (
                                    "Property values with their modification history, returned when "
                                    "propertiesWithHistory query parameter is used"
                                ),
                                "nullable": True,
                                "title": "Properties With History",
                                "type": "object",
                            },
                            "updatedAt": {
                                "description": "Timestamp of the most recent update, in ISO 8601 format",
                                "title": "Updated At",
                                "type": "string",
                            },
                            "url": {
                                "default": None,
                                "description": "Object URL reference",
                                "nullable": True,
                                "title": "Url",
                                "type": "string",
                            },
                        },
                        "required": [
                            "id",
                            "properties",
                            "createdAt",
                            "updatedAt",
                            "archived",
                        ],
                        "title": "ContactResult",
                        "type": "object",
                    },
                    "title": "Results",
                    "type": "array",
                },
                "startedAt": {
                    "description": "Timestamp when the batch processing began, in ISO 8601 format",
                    "title": "Started At",
                    "type": "string",
                },
                "status": {
                    "description": "The status of the batch operation. Valid values: PENDING, PROCESSING, CANCELED, COMPLETE",
                    "title": "Status",
                    "type": "string",
                },
            },
            "required": ["status", "results", "startedAt", "completedAt"],
            "title": "Data",
            "type": "object",
        },
        "error": {
            "default": None,
            "description": "Error if any occurred during the execution of the action",
            "nullable": True,
            "title": "Error",
            "type": "string",
        },
        "successful": {
            "description": "Whether or not the action execution was successful or not",
            "title": "Successful",
            "type": "boolean",
        },
    },
    "required": ["data", "successful"],
    "title": "UpdateABatchOfContactsResponseWrapper",
    "type": "object",
}


def hubspot_search_deals(
    context: "AgentContext",
    *,
    after: str | None = None,
    custom_properties: list[str] | None = None,
    filterGroups: list[dict[str, Any]] | None = None,
    limit: int | None = 5,
    properties: list[str] | None = None,
    query: str | None = None,
    sorts: list[dict[str, Any]] | None = None,
) -> ToolInvocationResult:
    """
    Description:
        Search HubSpot deals using query text, filters, sorting, and pagination.
    Args:
        after: Use the paging token from a previous response to continue where you left off.
        custom_properties: Include any custom deal fields (by their internal names) you want returned.
        filterGroups: Define advanced filters to narrow your search; filters within a group are ANDed, and groups are ORed.
            Filter properties: highValue, operator, propertyName, value, values.
        limit: Decide how many deals to return in one batch (higher numbers may take longer).
        properties: Choose which deal fields you want returned, including both standard and custom properties.
        query: Type keywords to find deals whose text fields contain them.
        sorts: Set the order of your results, like newest close date first or highest amount first. Sort properties:
            direction, propertyName.
    """
    provider = "hubspot"
    tool_name = "HUBSPOT_SEARCH_DEALS"
    ensure_authorized(context, provider)
    payload = _clean_payload(
        {
            "after": after,
            "custom_properties": custom_properties,
            "filterGroups": filterGroups,
            "limit": limit,
            "properties": properties,
            "query": query,
            "sorts": sorts,
        }
    )
    return _invoke_mcp_tool(context, provider, tool_name, payload)


hubspot_search_deals.__tb_output_schema__ = {
    "properties": {
        "data": {
            "additionalProperties": False,
            "description": "Data from the action execution",
            "properties": {
                "paging": {
                    "additionalProperties": False,
                    "default": None,
                    "description": (
                        "Pagination metadata for navigating through large result sets. Only present if additional "
                        "results exist beyond the current page."
                    ),
                    "nullable": True,
                    "properties": {
                        "next": {
                            "additionalProperties": False,
                            "default": None,
                            "description": (
                                "Contains pagination cursor for retrieving the next page of results. Only present "
                                "when additional results are available."
                            ),
                            "nullable": True,
                            "properties": {
                                "after": {
                                    "description": (
                                        "Cursor value to pass in the 'after' parameter of subsequent requests to "
                                        "retrieve the next page of results."
                                    ),
                                    "title": "After",
                                    "type": "string",
                                },
                                "link": {
                                    "default": None,
                                    "description": "URL query string containing the after parameter for the next page.",
                                    "nullable": True,
                                    "title": "Link",
                                    "type": "string",
                                },
                            },
                            "required": ["after"],
                            "title": "PagingNext",
                            "type": "object",
                        },
                        "prev": {
                            "additionalProperties": False,
                            "default": None,
                            "description": "Information for retrieving the previous page of results.",
                            "nullable": True,
                            "properties": {
                                "before": {
                                    "description": (
                                        "Cursor value to use in the request to retrieve the previous page of results."
                                    ),
                                    "title": "Before",
                                    "type": "string",
                                },
                                "link": {
                                    "default": None,
                                    "description": "URL query string containing the before parameter for the previous page.",
                                    "nullable": True,
                                    "title": "Link",
                                    "type": "string",
                                },
                            },
                            "required": ["before"],
                            "title": "PagingPrev",
                            "type": "object",
                        },
                    },
                    "title": "Paging",
                    "type": "object",
                },
                "results": {
                    "description": "Array of deal objects matching the search criteria.",
                    "items": {
                        "description": "Represents a single deal object matching the search criteria.",
                        "properties": {
                            "archived": {
                                "description": "Indicates whether the deal object is archived.",
                                "title": "Archived",
                                "type": "boolean",
                            },
                            "archivedAt": {
                                "default": None,
                                "description": (
                                    "Timestamp when the deal was archived, in ISO 8601 format. Present only if the "
                                    "deal is archived."
                                ),
                                "nullable": True,
                                "title": "Archived At",
                                "type": "string",
                            },
                            "createdAt": {
                                "description": (
                                    "Creation timestamp in ISO 8601 format (e.g., '2019-01-18T19:43:52.457Z')."
                                ),
                                "title": "Created At",
                                "type": "string",
                            },
                            "id": {
                                "description": "Unique identifier for the deal object.",
                                "title": "Id",
                                "type": "string",
                            },
                            "objectWriteTraceId": {
                                "default": None,
                                "description": "Internal trace identifier for write operations.",
                                "nullable": True,
                                "title": "Object Write Trace Id",
                                "type": "string",
                            },
                            "properties": {
                                "additionalProperties": {
                                    "anyOf": [
                                        {"type": "string"},
                                        {"type": "null"},
                                    ]
                                },
                                "description": (
                                    "Key-value pairs of deal properties. Default properties include createdate, "
                                    "hs_lastmodifieddate, and hs_object_id. Additional properties must be explicitly "
                                    "requested in the search request. Common deal properties include dealname, amount, "
                                    "closedate, pipeline, dealstage, hubspot_owner_id, deal_type, description, and "
                                    "various analytics and activity tracking properties."
                                ),
                                "title": "Properties",
                                "type": "object",
                            },
                            "propertiesWithHistory": {
                                "additionalProperties": {
                                    "items": {
                                        "description": "Represents a single historical change to a property.",
                                        "properties": {
                                            "sourceId": {
                                                "anyOf": [
                                                    {"type": "string"},
                                                    {"type": "null"},
                                                ],
                                                "default": None,
                                                "description": "Identifier of the source that made the change.",
                                                "title": "Sourceid",
                                            },
                                            "sourceLabel": {
                                                "anyOf": [
                                                    {"type": "string"},
                                                    {"type": "null"},
                                                ],
                                                "default": None,
                                                "description": "Human-readable label for the source.",
                                                "title": "Sourcelabel",
                                            },
                                            "sourceType": {
                                                "description": "The source type of the change.",
                                                "title": "Sourcetype",
                                                "type": "string",
                                            },
                                            "timestamp": {
                                                "description": "Timestamp when this value was set, in ISO 8601 format.",
                                                "title": "Timestamp",
                                                "type": "string",
                                            },
                                            "updatedByUserId": {
                                                "anyOf": [
                                                    {"type": "integer"},
                                                    {"type": "null"},
                                                ],
                                                "default": None,
                                                "description": "User ID of the person who updated this property.",
                                                "title": "Updatedbyuserid",
                                            },
                                            "value": {
                                                "description": "The property value at this point in history.",
                                                "title": "Value",
                                                "type": "string",
                                            },
                                        },
                                        "required": ["value", "timestamp", "sourceType"],
                                        "title": "PropertyHistoryItem",
                                        "type": "object",
                                    },
                                    "type": "array",
                                },
                                "default": None,
                                "description": (
                                    "Properties with change history metadata. Each property contains an array of "
                                    "historical values."
                                ),
                                "nullable": True,
                                "title": "Properties With History",
                                "type": "object",
                            },
                            "updatedAt": {
                                "description": (
                                    "Last modification timestamp in ISO 8601 format "
                                    "(e.g., '2022-05-24T14:49:32.259Z')."
                                ),
                                "title": "Updated At",
                                "type": "string",
                            },
                        },
                        "required": ["id", "properties", "createdAt", "updatedAt", "archived"],
                        "title": "DealResult",
                        "type": "object",
                    },
                    "title": "Results",
                    "type": "array",
                },
                "total": {
                    "description": "Total count of records matching the search criteria.",
                    "title": "Total",
                    "type": "integer",
                },
            },
            "required": ["total", "results"],
            "title": "Data",
            "type": "object",
        },
        "error": {
            "default": None,
            "description": "Error if any occurred during the execution of the action",
            "nullable": True,
            "title": "Error",
            "type": "string",
        },
        "successful": {
            "description": "Whether or not the action execution was successful or not",
            "title": "Successful",
            "type": "boolean",
        },
    },
    "required": ["data", "successful"],
    "title": "SearchDealsByCriteriaResponseWrapper",
    "type": "object",
}


def hubspot_search_contacts_by_criteria(
    context: "AgentContext",
    *,
    after: str | None = None,
    custom_properties: list[str] | None = None,
    filterGroups: list[dict[str, Any]] | None = None,
    limit: int | None = 5,
    properties: list[str] | None = None,
    query: str | None = None,
    sorts: list[dict[str, Any]] | None = None,
) -> ToolInvocationResult:
    """
    Description:
        Search HubSpot contacts using query text, filters, sorting, and pagination.
    Args:
        after: Use the paging token from a previous search to get the next page of results. Leave empty to start from the first page.
        custom_properties: Add the internal names of any custom contact fields you want returned. Use this to include data your team has added to HubSpot.
        filterGroups: Advanced filters (max 5 groups). Required if query is not provided. Filters in a group are ANDed; groups are ORed.
            Filter properties: highValue, operator, propertyName, value, values.
        limit: How many contacts to return in this search. Higher limits show more results per page.
        properties: Pick the contact fields you want returned, including both standard and custom properties. Including only what you need keeps responses concise.
        query: A quick text search across common contact fields. Required if filterGroups is not provided.
        sorts: Choose how the results should be ordered. Add one or more sort rules, such as last modified date descending.
            Sort properties: direction, propertyName.
    """
    provider = "hubspot"
    tool_name = "HUBSPOT_SEARCH_CONTACTS_BY_CRITERIA"
    ensure_authorized(context, provider)
    payload = _clean_payload(
        {
            "after": after,
            "custom_properties": custom_properties,
            "filterGroups": filterGroups,
            "limit": limit,
            "properties": properties,
            "query": query,
            "sorts": sorts,
        }
    )
    return _invoke_mcp_tool(context, provider, tool_name, payload)


hubspot_search_contacts_by_criteria.__tb_output_schema__ = {
    "properties": {
        "data": {
            "additionalProperties": False,
            "description": "Data from the action execution",
            "properties": {
                "paging": {
                    "additionalProperties": False,
                    "default": None,
                    "description": "Pagination metadata for navigating through result pages. Only present when additional results are available.",
                    "nullable": True,
                    "properties": {
                        "next": {
                            "additionalProperties": False,
                            "default": None,
                            "description": "Page reference information containing cursor token and optional link.",
                            "nullable": True,
                            "properties": {
                                "after": {
                                    "description": "A paging cursor token for retrieving subsequent/previous pages of results.",
                                    "title": "After",
                                    "type": "string",
                                },
                                "link": {
                                    "default": None,
                                    "description": "URL-formatted link to the next/previous page of results.",
                                    "nullable": True,
                                    "title": "Link",
                                    "type": "string",
                                },
                            },
                            "required": ["after"],
                            "title": "PagingReference",
                            "type": "object",
                        },
                        "prev": {
                            "additionalProperties": False,
                            "default": None,
                            "description": "Page reference information containing cursor token and optional link.",
                            "nullable": True,
                            "properties": {
                                "after": {
                                    "description": "A paging cursor token for retrieving subsequent/previous pages of results.",
                                    "title": "After",
                                    "type": "string",
                                },
                                "link": {
                                    "default": None,
                                    "description": "URL-formatted link to the next/previous page of results.",
                                    "nullable": True,
                                    "title": "Link",
                                    "type": "string",
                                },
                            },
                            "required": ["after"],
                            "title": "PagingReference",
                            "type": "object",
                        },
                    },
                    "title": "Paging",
                    "type": "object",
                },
                "results": {
                    "description": "Array of contact objects that match the search criteria.",
                    "items": {
                        "description": "A contact object that matches the search criteria.",
                        "properties": {
                            "archived": {
                                "description": "Whether the contact object is archived.",
                                "title": "Archived",
                                "type": "boolean",
                            },
                            "archivedAt": {
                                "default": None,
                                "description": "ISO 8601 timestamp when the contact was archived (only present if archived is true).",
                                "nullable": True,
                                "title": "Archived At",
                                "type": "string",
                            },
                            "createdAt": {
                                "description": "ISO 8601 timestamp when the contact was created.",
                                "title": "Created At",
                                "type": "string",
                            },
                            "id": {
                                "description": "The unique ID of the contact object.",
                                "title": "Id",
                                "type": "string",
                            },
                            "properties": {
                                "additionalProperties": True,
                                "description": (
                                    "Key-value pairs of contact properties. Default properties returned include "
                                    "createdate, email, firstname, hs_object_id, lastmodifieddate, and lastname. "
                                    "Additional properties can be requested."
                                ),
                                "properties": {
                                    "createdate": {
                                        "default": None,
                                        "description": "ISO 8601 timestamp when the contact was created (default property).",
                                        "nullable": True,
                                        "title": "Createdate",
                                        "type": "string",
                                    },
                                    "email": {
                                        "default": None,
                                        "description": "Email address of the contact (default property).",
                                        "nullable": True,
                                        "title": "Email",
                                        "type": "string",
                                    },
                                    "firstname": {
                                        "default": None,
                                        "description": "First name of the contact (default property).",
                                        "nullable": True,
                                        "title": "Firstname",
                                        "type": "string",
                                    },
                                    "hs_object_id": {
                                        "default": None,
                                        "description": "HubSpot object identifier for the contact (default property).",
                                        "nullable": True,
                                        "title": "Hs Object Id",
                                        "type": "string",
                                    },
                                    "lastmodifieddate": {
                                        "default": None,
                                        "description": "ISO 8601 timestamp when the contact was last modified (default property).",
                                        "nullable": True,
                                        "title": "Lastmodifieddate",
                                        "type": "string",
                                    },
                                    "lastname": {
                                        "default": None,
                                        "description": "Last name of the contact (default property).",
                                        "nullable": True,
                                        "title": "Lastname",
                                        "type": "string",
                                    },
                                },
                                "title": "Properties",
                                "type": "object",
                            },
                            "propertiesWithHistory": {
                                "additionalProperties": True,
                                "default": None,
                                "description": (
                                    "Property values with historical tracking information (only returned when "
                                    "specifically requested)."
                                ),
                                "nullable": True,
                                "title": "Properties With History",
                                "type": "object",
                            },
                            "updatedAt": {
                                "description": "ISO 8601 timestamp when the contact was last updated.",
                                "title": "Updated At",
                                "type": "string",
                            },
                        },
                        "required": ["id", "properties", "createdAt", "updatedAt", "archived"],
                        "title": "ContactResult",
                        "type": "object",
                    },
                    "title": "Results",
                    "type": "array",
                },
                "total": {
                    "description": "Total number of matching records available across all pages.",
                    "title": "Total",
                    "type": "integer",
                },
            },
            "required": ["total", "results"],
            "title": "Data",
            "type": "object",
        },
        "error": {
            "default": None,
            "description": "Error if any occurred during the execution of the action",
            "nullable": True,
            "title": "Error",
            "type": "string",
        },
        "successful": {
            "description": "Whether or not the action execution was successful or not",
            "title": "Successful",
            "type": "boolean",
        },
    },
    "required": ["data", "successful"],
    "title": "SearchContactsByCriteriaResponseWrapper",
    "type": "object",
}


def hubspot_list_deals(
    context: "AgentContext",
    *,
    after: str | None = None,
    archived: bool | None = False,
    associations: list[str] | None = None,
    limit: int | None = 10,
    properties: list[str] | None = None,
    propertiesWithHistory: list[str] | None = None,
) -> ToolInvocationResult:
    """
    Description:
        Retrieve a paginated list of HubSpot deals.
    Args:
        after: Use the token from the previous page of results to continue where you left off. Leave empty to start from the first page.
        archived: Whether to show archived deals. Set to true to list archived deals; leave false to see active deals.
        associations: Which related record types to include with each deal (e.g., contacts, companies). Adds their IDs so you can link deals to other objects.
        limit: How many deals to return per page. Maximum 100 normally, but limited to 50 when requesting properties with history.
        properties: Which deal fields you want included in each result (e.g., dealname, amount). Choose only what you need to keep responses concise.
        propertiesWithHistory: The deal fields for which you also want the change history. Helpful for seeing how values have changed over time.
    """
    provider = "hubspot"
    tool_name = "HUBSPOT_LIST_DEALS"
    ensure_authorized(context, provider)
    payload = _clean_payload(
        {
            "after": after,
            "archived": archived,
            "associations": associations,
            "limit": limit,
            "properties": properties,
            "propertiesWithHistory": propertiesWithHistory,
        }
    )
    return _invoke_mcp_tool(context, provider, tool_name, payload)


hubspot_list_deals.__tb_output_schema__ = {
    "properties": {
        "data": {
            "additionalProperties": False,
            "description": "Data from the action execution",
            "properties": {
                "paging": {
                    "additionalProperties": False,
                    "default": None,
                    "description": "Pagination information for navigating through multiple pages of results.",
                    "nullable": True,
                    "properties": {
                        "next": {
                            "additionalProperties": False,
                            "default": None,
                            "description": "Information for retrieving the next page of results.",
                            "nullable": True,
                            "properties": {
                                "after": {
                                    "description": (
                                        "Cursor value used to retrieve the next page of results. Pass this value as "
                                        "the 'after' query parameter in subsequent requests."
                                    ),
                                    "title": "After",
                                    "type": "string",
                                },
                                "link": {
                                    "default": None,
                                    "description": (
                                        "Full URL for fetching the next page of results, including the after parameter."
                                    ),
                                    "nullable": True,
                                    "title": "Link",
                                    "type": "string",
                                },
                            },
                            "required": ["after"],
                            "title": "NextPage",
                            "type": "object",
                        }
                    },
                    "title": "Paging",
                    "type": "object",
                },
                "results": {
                    "description": "Array of deal objects returned by the API.",
                    "items": {
                        "description": "Individual deal object with properties and metadata.",
                        "properties": {
                            "archived": {
                                "default": None,
                                "description": "Indicates whether the deal is archived (deleted).",
                                "nullable": True,
                                "title": "Archived",
                                "type": "boolean",
                            },
                            "archivedAt": {
                                "default": None,
                                "description": (
                                    "Timestamp when the deal was archived, in ISO 8601 format. Only present if the "
                                    "deal is archived."
                                ),
                                "nullable": True,
                                "title": "Archived At",
                                "type": "string",
                            },
                            "associations": {
                                "additionalProperties": {
                                    "description": "Associated object IDs grouped by object type.",
                                    "properties": {
                                        "paging": {
                                            "anyOf": [
                                                {
                                                    "description": "Pagination information for associations.",
                                                    "properties": {
                                                        "next": {
                                                            "anyOf": [
                                                                {
                                                                    "description": (
                                                                        "Information for retrieving the next page "
                                                                        "of associated records."
                                                                    ),
                                                                    "properties": {
                                                                        "after": {
                                                                            "description": (
                                                                                "Cursor value for retrieving the "
                                                                                "next page of results."
                                                                            ),
                                                                            "title": "After",
                                                                            "type": "string",
                                                                        },
                                                                        "link": {
                                                                            "anyOf": [
                                                                                {"type": "string"},
                                                                                {"type": "null"},
                                                                            ],
                                                                            "default": None,
                                                                            "description": (
                                                                                "Full URL for fetching the next page of "
                                                                                "results."
                                                                            ),
                                                                            "title": "Link",
                                                                        },
                                                                    },
                                                                    "required": ["after"],
                                                                    "title": "AssociationNextPage",
                                                                    "type": "object",
                                                                },
                                                                {"type": "null"},
                                                            ],
                                                            "default": None,
                                                            "description": (
                                                                "Contains information for retrieving the next page "
                                                                "of associated records."
                                                            ),
                                                        }
                                                    },
                                                    "title": "AssociationPaging",
                                                    "type": "object",
                                                },
                                                {"type": "null"},
                                            ],
                                            "default": None,
                                            "description": (
                                                "Pagination information for the associated records if there are more "
                                                "than can be returned in a single response."
                                            ),
                                        },
                                        "results": {
                                            "description": "Array of associated record IDs.",
                                            "items": {
                                                "description": "Associated object identifier.",
                                                "properties": {
                                                    "id": {
                                                        "description": "The ID of the associated record.",
                                                        "title": "Id",
                                                        "type": "string",
                                                    },
                                                    "type": {
                                                        "description": (
                                                            "The association type identifier (e.g., 'deal_to_contact', "
                                                            "'deal_to_company')."
                                                        ),
                                                        "title": "Type",
                                                        "type": "string",
                                                    },
                                                },
                                                "required": ["id", "type"],
                                                "title": "AssociationResult",
                                                "type": "object",
                                            },
                                            "title": "Results",
                                            "type": "array",
                                        },
                                    },
                                    "required": ["results"],
                                    "title": "Associations",
                                    "type": "object",
                                },
                                "default": None,
                                "description": (
                                    "Object containing associated records grouped by association type (e.g., contacts, "
                                    "companies). Only included if the associations query parameter is specified in the request."
                                ),
                                "nullable": True,
                                "title": "Associations",
                                "type": "object",
                            },
                            "createdAt": {
                                "description": "Timestamp when the deal was created, in ISO 8601 format.",
                                "title": "Created At",
                                "type": "string",
                            },
                            "id": {
                                "description": "Unique identifier for the deal.",
                                "title": "Id",
                                "type": "string",
                            },
                            "properties": {
                                "additionalProperties": {"type": "string"},
                                "description": (
                                    "Key-value pairs containing deal property values. Common properties include dealname, "
                                    "dealstage, pipeline, amount, closedate, createdate, hs_lastmodifieddate, hs_object_id, "
                                    "and hubspot_owner_id, among others. Custom properties may also be included."
                                ),
                                "title": "Properties",
                                "type": "object",
                            },
                            "propertiesWithHistory": {
                                "additionalProperties": {
                                    "items": {
                                        "description": "Historical value of a property at a specific point in time.",
                                        "properties": {
                                            "timestamp": {
                                                "description": "The timestamp when this value was set, in ISO 8601 format.",
                                                "title": "Timestamp",
                                                "type": "string",
                                            },
                                            "value": {
                                                "description": "The property value at a specific point in time.",
                                                "title": "Value",
                                                "type": "string",
                                            },
                                        },
                                        "required": ["value", "timestamp"],
                                        "title": "PropertyHistoryValue",
                                        "type": "object",
                                    },
                                    "type": "array",
                                },
                                "default": None,
                                "description": (
                                    "Object containing properties with their historical values and timestamps. Only "
                                    "included if the propertiesWithHistory query parameter is specified in the request."
                                ),
                                "nullable": True,
                                "title": "Properties With History",
                                "type": "object",
                            },
                            "updatedAt": {
                                "description": "Timestamp when the deal was last modified, in ISO 8601 format.",
                                "title": "Updated At",
                                "type": "string",
                            },
                        },
                        "required": ["id", "properties", "createdAt", "updatedAt"],
                        "title": "Deal",
                        "type": "object",
                    },
                    "title": "Results",
                    "type": "array",
                },
            },
            "required": ["results"],
            "title": "Data",
            "type": "object",
        },
        "error": {
            "default": None,
            "description": "Error if any occurred during the execution of the action",
            "nullable": True,
            "title": "Error",
            "type": "string",
        },
        "successful": {
            "description": "Whether or not the action execution was successful or not",
            "title": "Successful",
            "type": "boolean",
        },
    },
    "required": ["data", "successful"],
    "title": "ReadAPageOfDealsResponseWrapper",
    "type": "object",
}


def hubspot_list_contacts(
    context: "AgentContext",
    *,
    after: str | None = None,
    archived: bool | None = False,
    associations: list[str] | None = None,
    limit: int | None = 5,
    properties: list[str] | None = None,
    propertiesWithHistory: list[str] | None = None,
) -> ToolInvocationResult:
    """
    Description:
        Retrieve a paginated list of HubSpot contacts.
    Args:
        after: The value from the previous page to continue where you left off. Leave blank to start from the first page.
        archived: Choose whether to get archived contacts instead of active ones. Turn on to only see archived contacts.
        associations: Other record types you want to include IDs for with each contact, such as companies or deals. Helpful if you need related records alongside contacts.
        limit: How many contacts to fetch in this page. Choose a smaller number for quicker previews; up to 100 per page.
        properties: Which contact fields you want returned for each contact, like email or name. Pick only what you need to keep results focused.
        propertiesWithHistory: Contact fields for which you also want past values, not just the current one. Use this if you care about how a property changed over time.
    """
    provider = "hubspot"
    tool_name = "HUBSPOT_LIST_CONTACTS"
    ensure_authorized(context, provider)
    payload = _clean_payload(
        {
            "after": after,
            "archived": archived,
            "associations": associations,
            "limit": limit,
            "properties": properties,
            "propertiesWithHistory": propertiesWithHistory,
        }
    )
    return _invoke_mcp_tool(context, provider, tool_name, payload)


hubspot_list_contacts.__tb_output_schema__ = {
    "properties": {
        "data": {
            "additionalProperties": False,
            "description": "Data from the action execution",
            "properties": {
                "paging": {
                    "additionalProperties": False,
                    "default": None,
                    "description": (
                        "Navigation controls for pagination. Only included when there are additional pages of results."
                    ),
                    "nullable": True,
                    "properties": {
                        "next": {
                            "additionalProperties": False,
                            "default": None,
                            "description": "Next page navigation.",
                            "nullable": True,
                            "properties": {
                                "after": {
                                    "default": None,
                                    "description": "Cursor token for retrieving the next page of results.",
                                    "nullable": True,
                                    "title": "After",
                                    "type": "string",
                                },
                                "link": {
                                    "default": None,
                                    "description": "URL for the next page of results.",
                                    "nullable": True,
                                    "title": "Link",
                                    "type": "string",
                                },
                            },
                            "title": "PagingNext",
                            "type": "object",
                        },
                        "prev": {
                            "additionalProperties": False,
                            "default": None,
                            "description": "Previous page navigation.",
                            "nullable": True,
                            "properties": {
                                "before": {
                                    "default": None,
                                    "description": "Cursor token for retrieving the previous page of results.",
                                    "nullable": True,
                                    "title": "Before",
                                    "type": "string",
                                },
                                "link": {
                                    "default": None,
                                    "description": "URL for the previous page of results.",
                                    "nullable": True,
                                    "title": "Link",
                                    "type": "string",
                                },
                            },
                            "title": "PagingPrev",
                            "type": "object",
                        },
                    },
                    "title": "Paging",
                    "type": "object",
                },
                "results": {
                    "description": "Collection of contact objects returned by the API.",
                    "items": {
                        "description": "Individual contact object.",
                        "properties": {
                            "archived": {
                                "description": "Whether the object is archived.",
                                "title": "Archived",
                                "type": "boolean",
                            },
                            "archivedAt": {
                                "default": None,
                                "description": "The timestamp when the object was archived, in ISO 8601 format.",
                                "nullable": True,
                                "title": "Archived At",
                                "type": "string",
                            },
                            "associations": {
                                "additionalProperties": {
                                    "description": "Association group for a specific object type.",
                                    "properties": {
                                        "paging": {
                                            "anyOf": [
                                                {
                                                    "description": "Pagination information for associations.",
                                                    "properties": {
                                                        "next": {
                                                            "anyOf": [
                                                                {
                                                                    "description": "Next page navigation.",
                                                                    "properties": {
                                                                        "after": {
                                                                            "anyOf": [
                                                                                {"type": "string"},
                                                                                {"type": "null"},
                                                                            ],
                                                                            "default": None,
                                                                            "description": "Cursor token for the next page.",
                                                                            "title": "After",
                                                                        },
                                                                        "link": {
                                                                            "anyOf": [
                                                                                {"type": "string"},
                                                                                {"type": "null"},
                                                                            ],
                                                                            "default": None,
                                                                            "description": "URL for the next page.",
                                                                            "title": "Link",
                                                                        },
                                                                    },
                                                                    "title": "AssociationPagingNext",
                                                                    "type": "object",
                                                                },
                                                                {"type": "null"},
                                                            ],
                                                            "default": None,
                                                            "description": "Next page navigation.",
                                                        },
                                                        "prev": {
                                                            "anyOf": [
                                                                {
                                                                    "description": "Previous page navigation.",
                                                                    "properties": {
                                                                        "before": {
                                                                            "anyOf": [
                                                                                {"type": "string"},
                                                                                {"type": "null"},
                                                                            ],
                                                                            "default": None,
                                                                            "description": "Cursor token for the previous page.",
                                                                            "title": "Before",
                                                                        },
                                                                        "link": {
                                                                            "anyOf": [
                                                                                {"type": "string"},
                                                                                {"type": "null"},
                                                                            ],
                                                                            "default": None,
                                                                            "description": "URL for the previous page.",
                                                                            "title": "Link",
                                                                        },
                                                                    },
                                                                    "title": "AssociationPagingPrev",
                                                                    "type": "object",
                                                                },
                                                                {"type": "null"},
                                                            ],
                                                            "default": None,
                                                            "description": "Previous page navigation.",
                                                        },
                                                    },
                                                    "title": "AssociationPaging",
                                                    "type": "object",
                                                },
                                                {"type": "null"},
                                            ],
                                            "default": None,
                                            "description": "Pagination information for associations.",
                                        },
                                        "results": {
                                            "description": "Array of associated objects.",
                                            "items": {
                                                "description": "Individual association record.",
                                                "properties": {
                                                    "id": {
                                                        "description": "Association ID.",
                                                        "title": "Id",
                                                        "type": "string",
                                                    },
                                                    "type": {
                                                        "description": "Association type, formatted like 'deal_to_contact'.",
                                                        "title": "Type",
                                                        "type": "string",
                                                    },
                                                },
                                                "required": ["id", "type"],
                                                "title": "AssociationRecord",
                                                "type": "object",
                                            },
                                            "title": "Results",
                                            "type": "array",
                                        },
                                    },
                                    "required": ["results"],
                                    "title": "AssociationGroup",
                                    "type": "object",
                                },
                                "default": None,
                                "description": (
                                    "Related object connections organized by association type. Only included when "
                                    "requested via associations query parameter."
                                ),
                                "nullable": True,
                                "title": "Associations",
                                "type": "object",
                            },
                            "createdAt": {
                                "description": "The timestamp when the object was created, in ISO 8601 format.",
                                "title": "Created At",
                                "type": "string",
                            },
                            "id": {
                                "description": "The unique ID of the contact.",
                                "title": "Id",
                                "type": "string",
                            },
                            "objectWriteTraceId": {
                                "default": None,
                                "description": "Internal trace identifier.",
                                "nullable": True,
                                "title": "Object Write Trace Id",
                                "type": "string",
                            },
                            "properties": {
                                "additionalProperties": {
                                    "anyOf": [
                                        {"type": "string"},
                                        {"type": "null"},
                                    ]
                                },
                                "description": (
                                    "Key-value pairs representing contact attributes. Values can be strings or null."
                                ),
                                "title": "Properties",
                                "type": "object",
                            },
                            "propertiesWithHistory": {
                                "additionalProperties": {
                                    "items": {
                                        "description": "Historical value for a property.",
                                        "properties": {
                                            "sourceId": {
                                                "anyOf": [
                                                    {"type": "string"},
                                                    {"type": "null"},
                                                ],
                                                "default": None,
                                                "description": "Unique property identifier.",
                                                "title": "Sourceid",
                                            },
                                            "sourceLabel": {
                                                "anyOf": [
                                                    {"type": "string"},
                                                    {"type": "null"},
                                                ],
                                                "default": None,
                                                "description": "Human-readable label.",
                                                "title": "Sourcelabel",
                                            },
                                            "sourceType": {
                                                "anyOf": [
                                                    {"type": "string"},
                                                    {"type": "null"},
                                                ],
                                                "default": None,
                                                "description": "Property classification.",
                                                "title": "Sourcetype",
                                            },
                                            "timestamp": {
                                                "anyOf": [
                                                    {"type": "string"},
                                                    {"type": "null"},
                                                ],
                                                "default": None,
                                                "description": "Update timestamp in ISO 8601 format.",
                                                "title": "Timestamp",
                                            },
                                            "updatedByUserId": {
                                                "anyOf": [
                                                    {"type": "integer"},
                                                    {"type": "null"},
                                                ],
                                                "default": None,
                                                "description": "User who made the changes.",
                                                "title": "Updatedbyuserid",
                                            },
                                            "value": {
                                                "anyOf": [
                                                    {"type": "string"},
                                                    {"type": "null"},
                                                ],
                                                "default": None,
                                                "description": "Property value at this point in history.",
                                                "title": "Value",
                                            },
                                        },
                                        "title": "PropertyHistoryValue",
                                        "type": "object",
                                    },
                                    "type": "array",
                                },
                                "default": None,
                                "description": (
                                    "Historical property data including sourceType, timestamp, value, sourceId, sourceLabel, "
                                    "and updatedByUserId. Only included when requested via propertiesWithHistory query "
                                    "parameter."
                                ),
                                "nullable": True,
                                "title": "Properties With History",
                                "type": "object",
                            },
                            "updatedAt": {
                                "description": "The timestamp when the object was last updated, in ISO 8601 format.",
                                "title": "Updated At",
                                "type": "string",
                            },
                            "url": {
                                "default": None,
                                "description": "Contact record URL.",
                                "nullable": True,
                                "title": "Url",
                                "type": "string",
                            },
                        },
                        "required": ["id", "properties", "createdAt", "updatedAt", "archived"],
                        "title": "Contact",
                        "type": "object",
                    },
                    "title": "Results",
                    "type": "array",
                },
            },
            "required": ["results"],
            "title": "Data",
            "type": "object",
        },
        "error": {
            "default": None,
            "description": "Error if any occurred during the execution of the action",
            "nullable": True,
            "title": "Error",
            "type": "string",
        },
        "successful": {
            "description": "Whether or not the action execution was successful or not",
            "title": "Successful",
            "type": "boolean",
        },
    },
    "required": ["data", "successful"],
    "title": "ListContactsPageResponseWrapper",
    "type": "object",
}
