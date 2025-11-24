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
