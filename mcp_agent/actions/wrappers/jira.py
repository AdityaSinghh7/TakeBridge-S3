from __future__ import annotations

from typing import TYPE_CHECKING, List

from mcp_agent.types import ToolInvocationResult

from ._common import _clean_payload, _invoke_mcp_tool, ensure_authorized

if TYPE_CHECKING:
    from mcp_agent.core.context import AgentContext


def jira_create_issue(
    context: "AgentContext",
    project_key: str,
    summary: str,
    assignee: str | None = None,
    assignee_name: str | None = None,
    components: List[str] | None = None,
    description: str | None = None,
    due_date: str | None = None,
    environment: str | None = None,
    fix_versions: List[str] | None = None,
    issue_type: str = "Task",
    labels: List[str] | None = None,
    priority: str | None = None,
    reporter: str | None = None,
    sprint_id: int | None = None,
    versions: List[str] | None = None,
) -> ToolInvocationResult:
    """
    Create a new Jira issue in the specified project.

    Args:
        project_key: Jira project key.
        summary: Issue summary.
        assignee: Assignee account ID.
        assignee_name: Assignee name.
        components: Component list.
        description: Issue description.
        due_date: Due date string.
        environment: Environment value.
        fix_versions: Fix versions.
        issue_type: Issue type (default Task).
        labels: Labels.
        priority: Priority name.
        reporter: Reporter account ID.
        sprint_id: Sprint ID.
        versions: Affected versions.
    """
    provider = "jira"
    tool_name = "JIRA_CREATE_ISSUE"
    ensure_authorized(context, provider)
    payload = _clean_payload(
        {
            "project_key": project_key,
            "summary": summary,
            "assignee": assignee,
            "assignee_name": assignee_name,
            "components": components,
            "description": description,
            "due_date": due_date,
            "environment": environment,
            "fix_versions": fix_versions,
            "issue_type": issue_type,
            "labels": labels,
            "priority": priority,
            "reporter": reporter,
            "sprint_id": sprint_id,
            "versions": versions,
        }
    )
    return _invoke_mcp_tool(context, provider, tool_name, payload)

jira_create_issue.__tb_output_schema__ = {
  "properties": {
    "data": {
      "additionalProperties": False,
      "description": "Data from the action execution",
      "properties": {
        "browser_url": {
          "description": "Direct browser URL to view the created issue in the Jira web interface.",
          "examples": [
            "https://api.atlassian.com/ex/jira/cloud-id/browse/TEST-101"
          ],
          "title": "Browser Url",
          "type": "string"
        },
        "id": {
          "description": "Unique ID of the created Jira issue.",
          "examples": [
            "12738"
          ],
          "title": "Id",
          "type": "string"
        },
        "key": {
          "description": "Human-readable key of the created issue (e.g., 'PROJ-123').",
          "examples": [
            "TEST-101",
            "PROJ-42"
          ],
          "title": "Key",
          "type": "string"
        },
        "self": {
          "description": "Direct API URL to access the created issue via REST API.",
          "examples": [
            "https://api.atlassian.com/ex/jira/cloud-id/rest/api/3/issue/12738"
          ],
          "title": "Self",
          "type": "string"
        }
      },
      "required": [
        "id",
        "key",
        "browser_url",
        "self"
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
  "title": "CreateIssueResponseWrapper",
  "type": "object"
}
