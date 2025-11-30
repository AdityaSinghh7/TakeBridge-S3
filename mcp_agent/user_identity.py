"""User identity normalization utilities.

Minimal utility module - global user ID lookups have been replaced by AgentContext.
"""

from __future__ import annotations
import os
from typing import TYPE_CHECKING, Optional

_DEFAULT_USER_ID = "dev-local"
DEV_DEFAULT_USER_ID = _DEFAULT_USER_ID
DEV_USER_ENV_VAR = "TB_USER_ID"

if TYPE_CHECKING:
    from server.api.auth import CurrentUser

def normalize_user_id(user_id: Optional[str] = None) -> str:
    """
    Normalize a user ID, stripping whitespace and lowercasing.
    
    Args:
        user_id: Raw user identifier (may be None or empty)
    
    Returns:
        Normalized user ID (defaults to 'dev-local' if empty)
    """
    raw = (user_id or os.getenv(DEV_USER_ENV_VAR) or DEV_DEFAULT_USER_ID or "").strip()
    return raw.lower() if raw else DEV_DEFAULT_USER_ID

def resolve_dev_user_id(current_user: Optional["CurrentUser"] = None) -> str:
    """
    Resolve a user identifier for local development.
    
    Checks TB_USER_ID environment variable, then falls back to dev-local.
    
    Returns:
        Normalized user ID from environment or default
    """
    if current_user and getattr(current_user, "sub", None):
        return normalize_user_id(current_user.sub)
    return normalize_user_id(os.getenv(DEV_USER_ENV_VAR, DEV_DEFAULT_USER_ID))
