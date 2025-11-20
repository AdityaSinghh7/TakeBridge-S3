from __future__ import annotations

from typing import Any

from mcp_agent.agent.planner import MCPTaskResult, execute_mcp_task

from .user_identity import (
    DEV_DEFAULT_USER_ID,
    DEV_USER_ENV_VAR,
    normalize_user_id,
    resolve_dev_user_id,
)


def resolve_dev_user(user_id: str | None = None) -> str:
    """
    Resolve a user identifier for local development.

    Prefers an explicit `user_id`, then TB_USER_ID, and finally the stable
    dev default (DEV_DEFAULT_USER_ID).
    """
    if user_id is not None:
        return normalize_user_id(user_id)
    return resolve_dev_user_id()


def run_dev_task(task: str, *, user_id: str | None = None, **kwargs: Any) -> MCPTaskResult:
    """
    Convenience helper to exercise execute_mcp_task during local development.

    Args:
        task: Natural-language instruction for the planner.
        user_id: Optional override for the dev user identifier.
        **kwargs: Additional keyword arguments forwarded to execute_mcp_task.
    """
    resolved_user = resolve_dev_user(user_id)
    return execute_mcp_task(task, user_id=resolved_user, **kwargs)


__all__ = [
    "DEV_DEFAULT_USER_ID",
    "DEV_USER_ENV_VAR",
    "resolve_dev_user",
    "run_dev_task",
]

