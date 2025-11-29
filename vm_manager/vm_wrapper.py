# vm_manager/workspace_service.py

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from shared.db.engine import SessionLocal
from shared.db.models import Workspace, User
from shared.db import crud
from vm_manager.config import settings
from .aws_vm_manager import create_agent_instance_for_user, terminate_instance


def ensure_workspace(user_id: str) -> Workspace:
    """
    Get or create a workspace for this user_id.

    Args:
        user_id: Canonical Supabase user UUID (auth.users.id). This must be the same
                 across all clients (web app, widget, etc.) to ensure users get their
                 own workspace.

    Now backed by per-user EC2 Agent VMs:
      - If a workspace exists in DB: reuse it (for now, assume it's still running).
      - If none exists: create a new EC2 instance and record vm_instance_id + controller_base_url.
    """
    db: Session = SessionLocal()
    try:
        ws = (
            db.query(Workspace)
            .filter(Workspace.user_id == user_id)
            .order_by(Workspace.created_at.desc())
            .first()
        )

        now = datetime.now(timezone.utc)

        if ws:
            # TODO (later): check EC2 instance state and restart if needed
            ws.last_used_at = now
            db.commit()
            db.refresh(ws)
            return ws

        # Ensure User record exists in our database (for consistency with MCP connections)
        # This creates a User record if it doesn't exist, using the Supabase user_id
        crud.upsert_user(db, user_id)

        # No existing workspace: create a new Agent VM
        instance_id, controller_base_url, vnc_url = create_agent_instance_for_user(user_id)

        ws = Workspace(
            id=str(uuid.uuid4()),
            user_id=user_id,
            status="running",
            controller_base_url=controller_base_url,
            vnc_url=vnc_url,
            vm_instance_id=instance_id,
            cloud_region=settings.AWS_REGION,
            last_used_at=now,
        )
        db.add(ws)
        db.commit()
        db.refresh(ws)
        return ws
    finally:
        db.close()


def terminate_workspace_for_user(db: Session, user_id: str) -> Workspace | None:
    """
    Terminate the active workspace for a user.

    Finds the most recent running workspace for the user, terminates the EC2 instance,
    and marks the workspace as terminated in the database.

    Args:
        db: SQLAlchemy database session
        user_id: The user ID to terminate workspace for

    Returns:
        The terminated Workspace object, or None if no active workspace was found
    """
    ws = (
        db.query(Workspace)
        .filter(Workspace.user_id == user_id, Workspace.status == "running")
        .order_by(Workspace.created_at.desc())
        .first()
    )

    if ws is None:
        return None

    # If we have an instance, ask AWS to terminate it
    if ws.vm_instance_id:
        try:
            terminate_instance(ws.vm_instance_id)
        except Exception as e:
            # optional: log + maybe still mark as terminated
            print(f"[workspace_service] terminate_instance error: {e}")

    ws.status = "terminated"
    ws.controller_base_url = ""  # Empty string since column is nullable=False
    ws.vnc_url = None
    ws.updated_at = datetime.now(timezone.utc)
    db.add(ws)
    db.commit()
    db.refresh(ws)

    return ws
