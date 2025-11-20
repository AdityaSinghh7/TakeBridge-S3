"""User identity normalization utilities.

Minimal utility module - global user ID lookups have been replaced by AgentContext.
"""

from __future__ import annotations
import os


_DEFAULT_USER_ID = "dev-local"
DEV_DEFAULT_USER_ID = _DEFAULT_USER_ID
DEV_USER_ENV_VAR = "TB_USER_ID"


def normalize_user_id(user_id: str | None) -> str:
    """
    Normalize a user ID, stripping whitespace and lowercasing.
    
    Args:
        user_id: Raw user identifier (may be None or empty)
    
    Returns:
        Normalized user ID (defaults to 'dev-local' if empty)
    """
    if not user_id:
        return _DEFAULT_USER_ID
    if not isinstance(user_id, str):
        return _DEFAULT_USER_ID
    normalized = user_id.strip().lower()
    return normalized if normalized else _DEFAULT_USER_ID


def resolve_dev_user_id() -> str:
    """
    Resolve a user identifier for local development.
    
    Checks TB_USER_ID environment variable, then falls back to dev-local.
    
    Returns:
        Normalized user ID from environment or default
    """
    env_user = os.getenv(DEV_USER_ENV_VAR)
    return normalize_user_id(env_user)
