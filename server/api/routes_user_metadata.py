from __future__ import annotations

import json
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from server.api.auth import CurrentUser, get_current_user
from shared.db.engine import SessionLocal
from shared.db.sql import execute_text
from shared.db.user_metadata import default_user_metadata

router = APIRouter(prefix="/api", tags=["users"])


def _parse_json_dict(value: Any) -> Dict[str, Any]:
    if not value:
        return {}
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        try:
            loaded = json.loads(value)
            return loaded if isinstance(loaded, dict) else {}
        except Exception:
            return {}
    try:
        return dict(value)
    except Exception:
        return {}


@router.get("/users/{user_id}/metadata")
def get_user_metadata(
    user_id: str,
    current_user: CurrentUser = Depends(get_current_user),
) -> Dict[str, Any]:
    if str(current_user.sub) != str(user_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")

    db: Session = SessionLocal()
    try:
        row = execute_text(
            db,
            "SELECT metadata FROM users WHERE id = :user_id",
            {"user_id": user_id},
        ).scalar_one_or_none()
    finally:
        db.close()

    metadata = _parse_json_dict(row)
    if not metadata:
        metadata = default_user_metadata()
    return {"user_id": user_id, "metadata": metadata}


__all__ = ["router"]
