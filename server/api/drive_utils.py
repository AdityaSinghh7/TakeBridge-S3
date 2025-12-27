from __future__ import annotations

import posixpath
from typing import Optional

DRIVE_PREFIX = "drive"


def normalize_drive_path(
    raw_path: Optional[str],
    *,
    allow_empty: bool = False,
    allow_trailing_slash: bool = False,
) -> str:
    if raw_path is None:
        if allow_empty:
            return ""
        raise ValueError("drive_path_required")

    path = str(raw_path).strip()
    if not path:
        if allow_empty:
            return ""
        raise ValueError("drive_path_required")

    if path.startswith(("/", "\\")):
        raise ValueError("drive_path_absolute_not_allowed")

    path = path.replace("\\", "/")
    if not allow_trailing_slash and path.endswith("/"):
        raise ValueError("drive_path_must_not_end_with_slash")

    parts = [part for part in path.split("/") if part not in ("", ".")]
    if any(part == ".." for part in parts):
        raise ValueError("drive_path_traversal_not_allowed")

    normalized = "/".join(parts)
    if allow_trailing_slash and path.endswith("/") and normalized:
        normalized = f"{normalized}/"

    if not normalized and not allow_empty:
        raise ValueError("drive_path_required")

    return normalized


def build_drive_key(user_id: str, drive_path: str) -> str:
    if not user_id:
        raise ValueError("drive_user_id_required")
    if drive_path:
        return posixpath.join(str(user_id), DRIVE_PREFIX, drive_path)
    return f"{user_id}/{DRIVE_PREFIX}/"


def build_drive_prefix(user_id: str, prefix: str) -> str:
    if not prefix:
        return build_drive_key(user_id, "")
    base = build_drive_key(user_id, "")
    return f"{base}{prefix}"


def build_drive_backup_key(user_id: str, run_id: str, drive_path: str) -> str:
    if not user_id:
        raise ValueError("drive_user_id_required")
    if not run_id:
        raise ValueError("drive_run_id_required")
    if not drive_path:
        raise ValueError("drive_path_required")
    return posixpath.join(str(user_id), "drive_backups", str(run_id), drive_path)
