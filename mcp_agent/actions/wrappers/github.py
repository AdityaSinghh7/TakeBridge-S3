from __future__ import annotations

from typing import TYPE_CHECKING, List

from mcp_agent.types import ToolInvocationResult

from ._common import _clean_payload, _invoke_mcp_tool, ensure_authorized

if TYPE_CHECKING:
    from mcp_agent.core.context import AgentContext


def github_create_an_issue(
    context: "AgentContext",
    owner: str,
    repo: str,
    title: str,
    assignee: str | None = None,
    assignees: List[str] | None = None,
    body: str | None = None,
    labels: List[str] | None = None,
    milestone: str | None = None,
) -> ToolInvocationResult:
    """
    Create a new issue in a GitHub repository.

    Args:
        owner: Repository owner.
        repo: Repository name.
        title: Issue title.
        assignee: Single assignee.
        assignees: Multiple assignees.
        body: Issue body.
        labels: Labels to add.
        milestone: Milestone to assign.
    """
    provider = "github"
    tool_name = "GITHUB_CREATE_AN_ISSUE"
    ensure_authorized(context, provider)
    payload = _clean_payload(
        {
            "owner": owner,
            "repo": repo,
            "title": title,
            "assignee": assignee,
            "assignees": assignees,
            "body": body,
            "labels": labels,
            "milestone": milestone,
        }
    )
    return _invoke_mcp_tool(context, provider, tool_name, payload)


def github_issues_create_comment(
    context: "AgentContext",
    owner: str,
    repo: str,
    issue_number: int,
    body: str,
) -> ToolInvocationResult:
    """
    Create a comment on an existing GitHub issue or pull request.

    Args:
        owner: Repository owner.
        repo: Repository name.
        issue_number: Issue or pull request number.
        body: Comment body.
    """
    provider = "github"
    tool_name = "GITHUB_ISSUES_CREATE_COMMENT"
    ensure_authorized(context, provider)
    payload = _clean_payload(
        {
            "owner": owner,
            "repo": repo,
            "issue_number": issue_number,
            "body": body,
        }
    )
    return _invoke_mcp_tool(context, provider, tool_name, payload)
