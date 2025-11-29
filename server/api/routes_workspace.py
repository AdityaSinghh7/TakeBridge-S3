# server/api/routes_workspace.py

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session

from .auth import get_current_user, CurrentUser
from shared.db.engine import SessionLocal
from shared.db.models import Workspace
from server.schemas import WorkspaceOut
from server.core.workspace_service import terminate_workspace_for_user

router = APIRouter(prefix="/app", tags=["workspace"])


@router.get("/workspace", response_model=WorkspaceOut)
def get_workspace(current_user: CurrentUser = Depends(get_current_user)):
    """
    Return the most recent workspace for the authenticated user.

    This does NOT create a workspace or start a VM.
    It's purely introspection.

    Authentication: Requires a valid Supabase JWT token in the Authorization header.
    The user_id is extracted from the token (sub claim), ensuring the same user
    across web app, widget, and other clients gets the same workspace.

    Later, you can fill `status` more accurately and include VNC URL.
    """
    db: Session = SessionLocal()
    try:
        ws = (
            db.query(Workspace)
            .filter(Workspace.user_id == current_user.sub)
            .order_by(Workspace.created_at.desc())
            .first()
        )
        if not ws:
            raise HTTPException(status_code=404, detail="No workspace found for this user")
        return ws  # thanks to from_attributes=True, this works
    finally:
        db.close()


@router.post("/workspace/terminate", response_model=WorkspaceOut | dict)
def terminate_workspace(current_user: CurrentUser = Depends(get_current_user)):
    """
    Terminate the active workspace for the authenticated user.

    This will:
    - Find the most recent running workspace for the user
    - Terminate the associated EC2 instance
    - Mark the workspace as terminated in the database

    Authentication: Requires a valid Supabase JWT token in the Authorization header.
    The user_id is extracted from the token (sub claim).

    Returns:
        The terminated Workspace object, or {"status": "no_active_workspace"} if no active workspace was found
    """
    db: Session = SessionLocal()
    try:
        ws = terminate_workspace_for_user(db, user_id=current_user.sub)
        if ws is None:
            # no active workspace; return 200 with a message
            return {"status": "no_active_workspace"}
        return ws
    finally:
        db.close()

