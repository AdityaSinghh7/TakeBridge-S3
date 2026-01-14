"""GitHub action wrappers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from mcp_agent.types import ToolInvocationResult

from ._common import _clean_payload, _invoke_mcp_tool, ensure_authorized

if TYPE_CHECKING:
    from mcp_agent.core.context import AgentContext


def github_get_branch_protection(
    context: "AgentContext",
    owner: str,
    repo: str,
    branch: str,
) -> ToolInvocationResult:
    """
    Description:
        Retrieves branch protection settings for a specific, existing, and accessible branch in a GitHub repository; protection feature availability varies by GitHub product plan.
    Args:
        owner: (required) The username or organization that owns the repository you want to check. This tells us where to look for the branch.
        repo: (required) The name of the repository containing the branch. This specifies which project's branch protection you want to view.
        branch: (required) The exact branch you want to inspect (for example, 'main' or 'develop'). We use this to fetch the protection rules applied to that branch.
    """
    provider = "github"
    tool_name = "GITHUB_GET_BRANCH_PROTECTION"
    ensure_authorized(context, provider)
    payload = _clean_payload(
        {
            "owner": owner,
            "repo": repo,
            "branch": branch,
        }
    )
    return _invoke_mcp_tool(context, provider, tool_name, payload)


github_get_branch_protection.__tb_output_schema__ = {
    "properties": {
        "composio_execution_message": {
            "anyOf": [{"type": "string"}, {"type": "null"}],
            "default": None,
            "description": "Message explaining the execution result, especially when branch exists but has no protection rules.",
            "title": "Composio Execution Message",
        },
        "data": {
            "anyOf": [
                {
                    "additionalProperties": True,
                    "type": "object",
                },
                {"type": "null"},
            ],
            "default": None,
            "description": "Dictionary of branch protection settings; its structure varies based on enabled protections. Returns None if the branch exists but has no protection rules configured.",
            "title": "Data",
        },
        "error": {
            "anyOf": [{"type": "string"}, {"type": "null"}],
            "default": None,
            "description": "Error if any occurred during the execution of the action",
            "title": "Error",
        },
        "successful": {
            "description": "Whether or not the action execution was successful or not",
            "title": "Successful",
            "type": "boolean",
        },
    },
    "required": ["successful"],
    "title": "GetBranchProtectionResponseWrapper",
    "type": "object",
}


def github_search_issues_and_pull_requests(
    context: "AgentContext",
    q: str,
    order: str = "desc",
    page: int = 1,
    per_page: int = 30,
    raw_response: bool = False,
    sort: str | None = None,
) -> ToolInvocationResult:
    """
    Description:
        Searches GitHub for issues and pull requests. Use qualifiers to scope searches: `repo:owner/name` for specific repos, `org:orgname` for organizations, `user:username` for personal repos, `assignee:@me` for your assignments. Combine with `is:issue`, `is:pr`, `state:open`, `label:"name"` filters.
    Args:
        q: (required) The search keywords and filters you want to use on GitHub. You MUST include at least one search keyword (like 'bug', 'fix', 'error', etc.) in your query. Qualifiers like repo:, is:, label:, or author: are filters that narrow results, but cannot be the only content. Combine a keyword with qualifiers to find the exact issues or pull requests you need.
        order: (optional, default="desc") Pick whether the sort should be descending (newest/most first) or ascending. This only applies if you also choose a sort field.
        page: (optional, default=1) Which page of results to view, starting at 1. Use this to move through large result sets.
        per_page: (optional, default=30) How many results to show per page. Increase this to see more results at once (up to 100).
        raw_response: (optional, default=False) Return the full raw API payload instead of a simplified view. Turn this on if you need every field exactly as GitHub returns it.
        sort: (optional) Choose how the results should be sorted, like by comments or date. Leave blank to use GitHub’s best match.
    """
    provider = "github"
    tool_name = "GITHUB_SEARCH_ISSUES_AND_PULL_REQUESTS"
    ensure_authorized(context, provider)
    payload = _clean_payload(
        {
            "q": q,
            "order": order,
            "page": page,
            "per_page": per_page,
            "raw_response": raw_response,
            "sort": sort,
        }
    )
    return _invoke_mcp_tool(context, provider, tool_name, payload)


github_search_issues_and_pull_requests.__tb_output_schema__ = {
    "properties": {
        "data": {
            "additionalProperties": True,
            "description": "Dictionary with search results, including 'total_count', 'incomplete_results' (boolean indicating timeout), and 'items' (list of issue/pull request objects with their details).",
            "title": "Data",
            "type": "object",
        },
        "error": {
            "anyOf": [{"type": "string"}, {"type": "null"}],
            "default": None,
            "description": "Error if any occurred during the execution of the action",
            "title": "Error",
        },
        "successful": {
            "description": "Whether or not the action execution was successful or not",
            "title": "Successful",
            "type": "boolean",
        },
    },
    "required": ["data", "successful"],
    "title": "SearchIssuesAndPullRequestsResponseWrapper",
    "type": "object",
}


def github_list_pull_requests(
    context: "AgentContext",
    owner: str,
    repo: str,
    base: str | None = None,
    direction: str | None = None,
    head: str | None = None,
    page: int = 1,
    per_page: int = 30,
    sort: str = "created",
    state: str = "open",
) -> ToolInvocationResult:
    """
    Description:
        Lists pull requests for a GitHub repository. REQUIRES 'owner' AND 'repo' parameters - both are MANDATORY and must be provided in every call. Does NOT support filtering by assignee or date range - use GITHUB_FIND_PULL_REQUESTS instead for searching PRs by assignee, author, or across multiple repositories.
    Args:
        owner: (required) The GitHub username or organization that owns the repository you want to browse. This is a REQUIRED field - you must provide this value.
        repo: (required) The name of the repository you want to list pull requests for. This is a REQUIRED field - you must provide this value.
        base: (optional) Optionally filter by the target branch the PRs are merging into, like main or develop. Helpful to view PRs aimed at a specific release branch.
        direction: (optional) Choose ascending or descending order for the selected sort. If unsure, leave it blank to use the default for your sort choice.
        head: (optional) Optionally filter by the source branch (and user/org) the PRs come from, like user:feature-branch. Use this to see PRs created from a specific branch.
        page: (optional, default=1) Which page of results to view. Use this to navigate through large result sets.
        per_page: (optional, default=30) How many pull requests to show per page (up to 100). Increase this to see more results at once.
        sort: (optional, default="created") How you want the pull requests ordered (by creation time, last update, popularity, or long-running). Pick what makes it easiest to review.
        state: (optional, default="open") Choose which pull requests to see: open, closed, or all. This narrows the list to the status you care about.
    """
    provider = "github"
    tool_name = "GITHUB_LIST_PULL_REQUESTS"
    ensure_authorized(context, provider)
    payload = _clean_payload(
        {
            "owner": owner,
            "repo": repo,
            "base": base,
            "direction": direction,
            "head": head,
            "page": page,
            "per_page": per_page,
            "sort": sort,
            "state": state,
        }
    )
    return _invoke_mcp_tool(context, provider, tool_name, payload)


github_list_pull_requests.__tb_output_schema__ = {
    "properties": {
        "data": {
            "additionalProperties": True,
            "description": "Filtered pull request data with only essential information",
            "title": "Data",
            "type": "object",
        },
        "error": {
            "anyOf": [{"type": "string"}, {"type": "null"}],
            "default": None,
            "description": "Error if any occurred during the execution of the action",
            "title": "Error",
        },
        "successful": {
            "description": "Whether or not the action execution was successful or not",
            "title": "Successful",
            "type": "boolean",
        },
    },
    "required": ["data", "successful"],
    "title": "ListPullRequestsResponseWrapper",
    "type": "object",
}


def github_get_a_pull_request(
    context: "AgentContext",
    owner: str,
    repo: str,
    pull_number: int,
) -> ToolInvocationResult:
    """
    Description:
        Retrieves a specific pull request from a GitHub repository using its owner, repository name, and pull request number.
    Args:
        owner: (required) Enter the GitHub username or organization that owns the repository you want to check. This tells us which account the repository belongs to.
        repo: (required) Enter the exact repository name under that account (for example, Hello-World). This specifies which project you want to access.
        pull_number: (required) Provide the pull request number you want details for (the number shown like #1347). This selects the specific PR to retrieve.
    """
    provider = "github"
    tool_name = "GITHUB_GET_A_PULL_REQUEST"
    ensure_authorized(context, provider)
    payload = _clean_payload(
        {
            "owner": owner,
            "repo": repo,
            "pull_number": pull_number,
        }
    )
    return _invoke_mcp_tool(context, provider, tool_name, payload)


github_get_a_pull_request.__tb_output_schema__ = {
    "properties": {
        "data": {
            "additionalProperties": True,
            "title": "Data",
            "type": "object",
        },
        "error": {
            "anyOf": [{"type": "string"}, {"type": "null"}],
            "default": None,
            "description": "Error if any occurred during the execution of the action",
            "title": "Error",
        },
        "successful": {
            "description": "Whether or not the action execution was successful or not",
            "title": "Successful",
            "type": "boolean",
        },
    },
    "required": ["data", "successful"],
    "title": "GetAPullRequestResponseWrapper",
    "type": "object",
}


def github_list_reviews_for_a_pull_request(
    context: "AgentContext",
    owner: str,
    repo: str,
    pull_number: int,
    page: int = 1,
    per_page: int = 30,
) -> ToolInvocationResult:
    """
    Description:
        Lists submitted reviews chronologically for a specific pull request within a GitHub repository.
    Args:
        owner: (required) The GitHub username or organization that owns the repository with the pull request. This tells us which account to search in.
        repo: (required) The repository name under that account where the pull request exists. Use the short name (without .git).
        pull_number: (required) The number of the pull request you want to view reviews for. You can copy it from the PR URL or title in GitHub.
        page: (optional, default=1) Which page of results to fetch. Increase this to move through additional pages of reviews.
        per_page: (optional, default=30) How many review entries to return per page. Choose up to 100 if you want to see more results at once.
    """
    provider = "github"
    tool_name = "GITHUB_LIST_REVIEWS_FOR_A_PULL_REQUEST"
    ensure_authorized(context, provider)
    payload = _clean_payload(
        {
            "owner": owner,
            "repo": repo,
            "pull_number": pull_number,
            "page": page,
            "per_page": per_page,
        }
    )
    return _invoke_mcp_tool(context, provider, tool_name, payload)


github_list_reviews_for_a_pull_request.__tb_output_schema__ = {
    "properties": {
        "data": {
            "additionalProperties": True,
            "title": "Data",
            "type": "object",
        },
        "error": {
            "anyOf": [{"type": "string"}, {"type": "null"}],
            "default": None,
            "description": "Error if any occurred during the execution of the action",
            "title": "Error",
        },
        "successful": {
            "description": "Whether or not the action execution was successful or not",
            "title": "Successful",
            "type": "boolean",
        },
    },
    "required": ["data", "successful"],
    "title": "ListReviewsForAPullRequestResponseWrapper",
    "type": "object",
}


def github_list_review_comments_on_a_pull_request(
    context: "AgentContext",
    owner: str,
    repo: str,
    pull_number: int,
    direction: str | None = None,
    page: int = 1,
    per_page: int = 30,
    since: str | None = None,
    sort: str = "created",
) -> ToolInvocationResult:
    """
    Description:
        Lists all review comments on a specific pull request within a GitHub repository.
    Args:
        owner: (required) The account name of the person or organization that owns the repository. This tells us where to look for the pull request.
        repo: (required) The name of the repository that contains the pull request. This specifies the project you want to get comments from.
        pull_number: (required) The number of the pull request you want to see comments for. You can find this in the PR’s URL or title.
        direction: (optional) Pick ascending or descending order for the sort. Valid values are 'asc' (ascending) or 'desc' (descending). Use 'desc' to see the newest items first.
        page: (optional, default=1) Which page of results to show. Use this to move through multiple pages of comments.
        per_page: (optional, default=30) How many comments to return per page. Increase this to see more results at once (up to 100).
        since: (optional) Show only comments updated on or after this date and time. Use this to filter out older activity.
        sort: (optional, default="created") Choose whether to order comments by when they were created or when they were last updated.
    """
    provider = "github"
    tool_name = "GITHUB_LIST_REVIEW_COMMENTS_ON_A_PULL_REQUEST"
    ensure_authorized(context, provider)
    payload = _clean_payload(
        {
            "owner": owner,
            "repo": repo,
            "pull_number": pull_number,
            "direction": direction,
            "page": page,
            "per_page": per_page,
            "since": since,
            "sort": sort,
        }
    )
    return _invoke_mcp_tool(context, provider, tool_name, payload)


github_list_review_comments_on_a_pull_request.__tb_output_schema__ = {
    "properties": {
        "data": {
            "additionalProperties": True,
            "title": "Data",
            "type": "object",
        },
        "error": {
            "anyOf": [{"type": "string"}, {"type": "null"}],
            "default": None,
            "description": "Error if any occurred during the execution of the action",
            "title": "Error",
        },
        "successful": {
            "description": "Whether or not the action execution was successful or not",
            "title": "Successful",
            "type": "boolean",
        },
    },
    "required": ["data", "successful"],
    "title": "ListReviewCommentsOnAPullRequestResponseWrapper",
    "type": "object",
}


def github_list_check_runs_for_a_ref(
    context: "AgentContext",
    owner: str,
    repo: str,
    ref: str,
    app_id: int | None = None,
    check_name: str | None = None,
    filter: str | None = "latest",
    page: int | None = 1,
    per_page: int | None = 30,
    status: str | None = None,
) -> ToolInvocationResult:
    """
    Description:
        List GitHub check runs for a commit SHA, branch, or tag to assess CI status and conclusions. Use when you need reliable CI pass/fail signals beyond commit metadata.
    Args:
        owner: (required) The account owner of the repository (username or organization name). Case-insensitive.
        repo: (required) The name of the repository without .git extension. Case-insensitive.
        ref: (required) The git reference - can be a commit SHA, branch name, or tag name.
        app_id: (optional) Filter by GitHub App identifier.
        check_name: (optional) Filters results to check runs with the specified name.
        filter: (optional, default="latest") Filter by completion timestamp: 'latest' returns the most recent check runs, 'all' returns all check runs.
        page: (optional, default=1) Page number of results to fetch.
        per_page: (optional, default=30) Number of results per page, maximum 100.
        status: (optional) Filter by check run status: queued, in_progress, or completed.
    """
    provider = "github"
    tool_name = "GITHUB_LIST_CHECK_RUNS_FOR_A_REF"
    ensure_authorized(context, provider)
    payload = _clean_payload(
        {
            "owner": owner,
            "repo": repo,
            "ref": ref,
            "app_id": app_id,
            "check_name": check_name,
            "filter": filter,
            "page": page,
            "per_page": per_page,
            "status": status,
        }
    )
    return _invoke_mcp_tool(context, provider, tool_name, payload)


github_list_check_runs_for_a_ref.__tb_output_schema__ = {
    "properties": {
        "data": {
            "additionalProperties": False,
            "description": "Data from the action execution",
            "properties": {
                "check_runs": {
                    "anyOf": [
                        {
                            "items": {
                                "properties": {
                                    "app": {
                                        "anyOf": [
                                            {
                                                "properties": {
                                                    "created_at": {
                                                        "anyOf": [
                                                            {"type": "string"},
                                                            {"type": "null"},
                                                        ],
                                                        "default": None,
                                                        "description": "The creation timestamp of the GitHub App.",
                                                        "title": "Created At",
                                                    },
                                                    "description": {
                                                        "anyOf": [
                                                            {"type": "string"},
                                                            {"type": "null"},
                                                        ],
                                                        "default": None,
                                                        "description": "The description of the GitHub App.",
                                                        "title": "Description",
                                                    },
                                                    "external_url": {
                                                        "anyOf": [
                                                            {"type": "string"},
                                                            {"type": "null"},
                                                        ],
                                                        "default": None,
                                                        "description": "The external URL for the GitHub App.",
                                                        "title": "External Url",
                                                    },
                                                    "html_url": {
                                                        "anyOf": [
                                                            {"type": "string"},
                                                            {"type": "null"},
                                                        ],
                                                        "default": None,
                                                        "description": "The HTML URL for the GitHub App.",
                                                        "title": "Html Url",
                                                    },
                                                    "id": {
                                                        "anyOf": [
                                                            {"type": "integer"},
                                                            {"type": "null"},
                                                        ],
                                                        "default": None,
                                                        "description": "The unique identifier of the GitHub App.",
                                                        "title": "Id",
                                                    },
                                                    "name": {
                                                        "anyOf": [
                                                            {"type": "string"},
                                                            {"type": "null"},
                                                        ],
                                                        "default": None,
                                                        "description": "The name of the GitHub App.",
                                                        "title": "Name",
                                                    },
                                                    "node_id": {
                                                        "anyOf": [
                                                            {"type": "string"},
                                                            {"type": "null"},
                                                        ],
                                                        "default": None,
                                                        "description": "The node identifier for the GitHub App.",
                                                        "title": "Node Id",
                                                    },
                                                    "owner": {
                                                        "anyOf": [
                                                            {
                                                                "properties": {
                                                                    "avatar_url": {
                                                                        "anyOf": [
                                                                            {"type": "string"},
                                                                            {"type": "null"},
                                                                        ],
                                                                        "default": None,
                                                                        "description": "The avatar URL of the owner.",
                                                                        "title": "Avatar Url",
                                                                    },
                                                                    "id": {
                                                                        "anyOf": [
                                                                            {"type": "integer"},
                                                                            {"type": "null"},
                                                                        ],
                                                                        "default": None,
                                                                        "description": "The unique identifier of the owner.",
                                                                        "title": "Id",
                                                                    },
                                                                    "login": {
                                                                        "anyOf": [
                                                                            {"type": "string"},
                                                                            {"type": "null"},
                                                                        ],
                                                                        "default": None,
                                                                        "description": "The login name of the owner.",
                                                                        "title": "Login",
                                                                    },
                                                                    "node_id": {
                                                                        "anyOf": [
                                                                            {"type": "string"},
                                                                            {"type": "null"},
                                                                        ],
                                                                        "default": None,
                                                                        "description": "The node identifier of the owner.",
                                                                        "title": "Node Id",
                                                                    },
                                                                    "type": {
                                                                        "anyOf": [
                                                                            {"type": "string"},
                                                                            {"type": "null"},
                                                                        ],
                                                                        "default": None,
                                                                        "description": "The type of the owner (User or Organization).",
                                                                        "title": "Type",
                                                                    },
                                                                },
                                                                "title": "CheckRunAppOwner",
                                                                "type": "object",
                                                            },
                                                            {"type": "null"},
                                                        ],
                                                        "default": None,
                                                        "description": "The owner of the GitHub App.",
                                                    },
                                                    "slug": {
                                                        "anyOf": [
                                                            {"type": "string"},
                                                            {"type": "null"},
                                                        ],
                                                        "default": None,
                                                        "description": "The slug name of the GitHub App.",
                                                        "title": "Slug",
                                                    },
                                                    "updated_at": {
                                                        "anyOf": [
                                                            {"type": "string"},
                                                            {"type": "null"},
                                                        ],
                                                        "default": None,
                                                        "description": "The last update timestamp of the GitHub App.",
                                                        "title": "Updated At",
                                                    },
                                                },
                                                "title": "CheckRunApp",
                                                "type": "object",
                                            },
                                            {"type": "null"},
                                        ],
                                        "default": None,
                                        "description": "The GitHub App that created this check run.",
                                    },
                                    "check_suite": {
                                        "anyOf": [
                                            {
                                                "properties": {
                                                    "id": {
                                                        "anyOf": [
                                                            {"type": "integer"},
                                                            {"type": "null"},
                                                        ],
                                                        "default": None,
                                                        "description": "The unique identifier of the check suite.",
                                                        "title": "Id",
                                                    }
                                                },
                                                "title": "CheckRunCheckSuite",
                                                "type": "object",
                                            },
                                            {"type": "null"},
                                        ],
                                        "default": None,
                                        "description": "The check suite this check run belongs to.",
                                    },
                                    "completed_at": {
                                        "anyOf": [
                                            {"type": "string"},
                                            {"type": "null"},
                                        ],
                                        "default": None,
                                        "description": "The ISO 8601 timestamp when the check run completed.",
                                        "title": "Completed At",
                                    },
                                    "conclusion": {
                                        "anyOf": [
                                            {"type": "string"},
                                            {"type": "null"},
                                        ],
                                        "default": None,
                                        "description": "The conclusion of the check run (success, failure, neutral, cancelled, skipped, timed_out, action_required).",
                                        "title": "Conclusion",
                                    },
                                    "details_url": {
                                        "anyOf": [
                                            {"type": "string"},
                                            {"type": "null"},
                                        ],
                                        "default": None,
                                        "description": "The URL with detailed information about the check run.",
                                        "title": "Details Url",
                                    },
                                    "external_id": {
                                        "anyOf": [
                                            {"type": "string"},
                                            {"type": "null"},
                                        ],
                                        "default": None,
                                        "description": "The external identifier for the check run.",
                                        "title": "External Id",
                                    },
                                    "head_sha": {
                                        "anyOf": [
                                            {"type": "string"},
                                            {"type": "null"},
                                        ],
                                        "default": None,
                                        "description": "The SHA of the commit this check run is for.",
                                        "title": "Head Sha",
                                    },
                                    "html_url": {
                                        "anyOf": [
                                            {"type": "string"},
                                            {"type": "null"},
                                        ],
                                        "default": None,
                                        "description": "The HTML URL to view the check run on GitHub.",
                                        "title": "Html Url",
                                    },
                                    "id": {
                                        "anyOf": [
                                            {"type": "integer"},
                                            {"type": "null"},
                                        ],
                                        "default": None,
                                        "description": "The unique identifier of the check run.",
                                        "title": "Id",
                                    },
                                    "name": {
                                        "anyOf": [
                                            {"type": "string"},
                                            {"type": "null"},
                                        ],
                                        "default": None,
                                        "description": "The name of the check run.",
                                        "title": "Name",
                                    },
                                    "node_id": {
                                        "anyOf": [
                                            {"type": "string"},
                                            {"type": "null"},
                                        ],
                                        "default": None,
                                        "description": "The node identifier for the check run.",
                                        "title": "Node Id",
                                    },
                                    "output": {
                                        "anyOf": [
                                            {
                                                "properties": {
                                                    "annotations_count": {
                                                        "anyOf": [
                                                            {"type": "integer"},
                                                            {"type": "null"},
                                                        ],
                                                        "default": None,
                                                        "description": "The number of annotations in the check run.",
                                                        "title": "Annotations Count",
                                                    },
                                                    "annotations_url": {
                                                        "anyOf": [
                                                            {"type": "string"},
                                                            {"type": "null"},
                                                        ],
                                                        "default": None,
                                                        "description": "The API URL for annotations.",
                                                        "title": "Annotations Url",
                                                    },
                                                    "summary": {
                                                        "anyOf": [
                                                            {"type": "string"},
                                                            {"type": "null"},
                                                        ],
                                                        "default": None,
                                                        "description": "The summary of the check run output.",
                                                        "title": "Summary",
                                                    },
                                                    "text": {
                                                        "anyOf": [
                                                            {"type": "string"},
                                                            {"type": "null"},
                                                        ],
                                                        "default": None,
                                                        "description": "The detailed output text.",
                                                        "title": "Text",
                                                    },
                                                    "title": {
                                                        "anyOf": [
                                                            {"type": "string"},
                                                            {"type": "null"},
                                                        ],
                                                        "default": None,
                                                        "description": "The title of the check run output.",
                                                        "title": "Title",
                                                    },
                                                },
                                                "title": "CheckRunOutput",
                                                "type": "object",
                                            },
                                            {"type": "null"},
                                        ],
                                        "default": None,
                                        "description": "The output details of the check run including title, summary, and annotations.",
                                    },
                                    "pull_requests": {
                                        "anyOf": [
                                            {
                                                "items": {
                                                    "additionalProperties": {"type": "string"},
                                                    "type": "object",
                                                },
                                                "type": "array",
                                            },
                                            {"type": "null"},
                                        ],
                                        "default": None,
                                        "description": "List of pull requests associated with this check run.",
                                        "title": "Pull Requests",
                                    },
                                    "started_at": {
                                        "anyOf": [
                                            {"type": "string"},
                                            {"type": "null"},
                                        ],
                                        "default": None,
                                        "description": "The ISO 8601 timestamp when the check run started.",
                                        "title": "Started At",
                                    },
                                    "status": {
                                        "anyOf": [
                                            {"type": "string"},
                                            {"type": "null"},
                                        ],
                                        "default": None,
                                        "description": "The status of the check run (queued, in_progress, completed, waiting, requested, pending).",
                                        "title": "Status",
                                    },
                                    "url": {
                                        "anyOf": [
                                            {"type": "string"},
                                            {"type": "null"},
                                        ],
                                        "default": None,
                                        "description": "The API URL for the check run.",
                                        "title": "Url",
                                    },
                                },
                                "title": "CheckRun",
                                "type": "object",
                            },
                            "type": "array",
                        },
                        {"type": "null"},
                    ],
                    "default": None,
                    "description": "List of check runs for the specified git reference.",
                    "title": "Check Runs",
                },
                "total_count": {
                    "anyOf": [
                        {"type": "integer"},
                        {"type": "null"},
                    ],
                    "default": None,
                    "description": "The total number of check runs matching the query.",
                    "title": "Total Count",
                },
            },
            "title": "Data",
            "type": "object",
        },
        "error": {
            "anyOf": [{"type": "string"}, {"type": "null"}],
            "default": None,
            "description": "Error if any occurred during the execution of the action",
            "title": "Error",
        },
        "successful": {
            "description": "Whether or not the action execution was successful or not",
            "title": "Successful",
            "type": "boolean",
        },
    },
    "required": ["data", "successful"],
    "title": "ListCheckRunsForARefResponseWrapper",
    "type": "object",
}


def github_run_graph_ql_query(
    context: "AgentContext",
    query: str,
    variables: dict | None = None,
) -> ToolInvocationResult:
    """
    Description:
        Tool to run an arbitrary GitHub GraphQL v4 query. Use when you need to fetch multiple datasets in one batch.
    Args:
        query: (required) The GraphQL operation (query or mutation) as a single string. Must be valid against GitHub's v4 schema.
        variables: (optional) Optional mapping of variable names to values referenced in the query (omit if none).
    """
    provider = "github"
    tool_name = "GITHUB_RUN_GRAPH_QL_QUERY"
    ensure_authorized(context, provider)
    payload = _clean_payload({"query": query, "variables": variables})
    return _invoke_mcp_tool(context, provider, tool_name, payload)


github_run_graph_ql_query.__tb_output_schema__ = {
    "properties": {
        "data": {
            "anyOf": [
                {"additionalProperties": True, "type": "object"},
                {"type": "null"},
            ],
            "default": None,
            "description": "Result data matching the query shape; null if execution fails entirely",
            "title": "Data",
        },
        "error": {
            "anyOf": [{"type": "string"}, {"type": "null"}],
            "default": None,
            "description": "Error if any occurred during the execution of the action",
            "title": "Error",
        },
        "errors": {
            "anyOf": [
                {
                    "items": {
                        "description": "Detailed information about a GraphQL execution error.",
                        "properties": {
                            "locations": {
                                "anyOf": [
                                    {
                                        "items": {
                                            "description": "Location of a GraphQL error in the query document.",
                                            "properties": {
                                                "column": {
                                                    "description": "1-based column number where the error occurred",
                                                    "minimum": 1,
                                                    "title": "Column",
                                                    "type": "integer",
                                                },
                                                "line": {
                                                    "description": "1-based line number where the error occurred",
                                                    "minimum": 1,
                                                    "title": "Line",
                                                    "type": "integer",
                                                },
                                            },
                                            "required": ["line", "column"],
                                            "title": "GraphQLErrorLocation",
                                            "type": "object",
                                        },
                                        "type": "array",
                                    },
                                    {"type": "null"},
                                ],
                                "default": None,
                                "description": "List of positions in the query document corresponding to this error",
                                "title": "Locations",
                            },
                            "message": {
                                "description": "Human-readable error message returned by GraphQL",
                                "title": "Message",
                                "type": "string",
                            },
                        },
                        "required": ["message"],
                        "title": "GraphQLError",
                        "type": "object",
                    },
                    "type": "array",
                },
                {"type": "null"},
            ],
            "default": None,
            "description": "List of errors returned by the GraphQL endpoint, if any",
            "title": "Errors",
        },
        "successful": {
            "description": "Whether or not the action execution was successful or not",
            "title": "Successful",
            "type": "boolean",
        },
    },
    "required": ["successful"],
    "title": "RunGraphQLQueryResponseWrapper",
    "type": "object",
}
