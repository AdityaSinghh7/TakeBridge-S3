from __future__ import annotations

import os

DEV_USER_ENV_VAR = "TB_USER_ID"
DEV_DEFAULT_USER_ID = "dev-local"


def normalize_user_id(user_id: str) -> str:
    """Normalize and validate user identifiers."""
    if not isinstance(user_id, str):
        raise TypeError("user_id must be a string.")
    trimmed = user_id.strip()
    if not trimmed:
        raise ValueError("user_id cannot be empty or whitespace.")
    return trimmed


def ensure_user_id(user_id: str | None) -> str:
    """Require that a user identifier is provided."""
    if user_id is None:
        raise ValueError("user_id is required.")
    return normalize_user_id(user_id)


def require_env_user_id(env_var: str = DEV_USER_ENV_VAR) -> str:
    """Resolve the active user id from the environment, raising when missing."""
    raw = os.getenv(env_var)
    if raw is None or not raw.strip():
        raise RuntimeError(
            f"{env_var} is not set. Export a stable user id before invoking MCP helpers."
        )
    return normalize_user_id(raw)


def resolve_dev_user_id(default: str = DEV_DEFAULT_USER_ID) -> str:
    """Return TB_USER_ID or a stable dev default for local harnesses."""
    raw = os.getenv(DEV_USER_ENV_VAR, "").strip() or default
    return normalize_user_id(raw)

