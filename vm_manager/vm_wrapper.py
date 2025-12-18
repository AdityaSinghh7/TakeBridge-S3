# vm_manager/workspace_service.py

import json
import uuid
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

from shared.db.engine import SessionLocal
from shared.db.models import Workspace, User
from shared.db import crud
from vm_manager.config import settings
from .aws_vm_manager import create_agent_instance_for_user, stop_instance, terminate_instance


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


def stop_run_instance(run_id: str, *, wait: bool = True) -> str:
    """
    Stop (power off) the EC2 instance associated with a workflow run.

    This looks up `workflow_runs.environment.endpoint.instance_id` for the run_id,
    calls `aws_vm_manager.stop_instance(...)`, and records the stop time in
    `vm_instances.stopped_at` (if a matching vm_instances row exists).

    Returns:
        The AWS EC2 instance_id that was stopped.
    """
    # Phase 1: fetch the run's instance_id without holding a long-lived transaction.
    db: Session = SessionLocal()
    vm_id: str | None = None
    instance_id: str | None = None
    try:
        row = (
            db.execute(
                text("SELECT environment, vm_id FROM workflow_runs WHERE id = :run_id"),
                {"run_id": run_id},
            )
            .mappings()
            .first()
        )
        if not row:
            raise RuntimeError("run_not_found")

        vm_id = str(row.get("vm_id")) if row.get("vm_id") else None

        env_raw = row.get("environment")
        if isinstance(env_raw, dict):
            environment = dict(env_raw)
        elif isinstance(env_raw, str) and env_raw.strip():
            try:
                environment = json.loads(env_raw) or {}
            except Exception:
                environment = {}
        else:
            environment = {}

        endpoint = environment.get("endpoint") or {}
        if isinstance(endpoint, str) and endpoint.strip():
            try:
                endpoint = json.loads(endpoint) or {}
            except Exception:
                endpoint = {}

        if isinstance(endpoint, dict) and endpoint.get("instance_id"):
            instance_id = str(endpoint["instance_id"])

        if not instance_id:
            candidate_rows = []
            if vm_id:
                candidate_rows.append(
                    db.execute(
                        text("SELECT endpoint FROM vm_instances WHERE id = :vm_id"),
                        {"vm_id": vm_id},
                    ).scalar_one_or_none()
                )
            candidate_rows.append(
                db.execute(
                    text(
                        """
                        SELECT endpoint
                        FROM vm_instances
                        WHERE run_id = :run_id
                        ORDER BY created_at DESC
                        LIMIT 1
                        """
                    ),
                    {"run_id": run_id},
                ).scalar_one_or_none()
            )
            for candidate in candidate_rows:
                if not candidate:
                    continue
                if isinstance(candidate, dict):
                    candidate_endpoint = candidate
                elif isinstance(candidate, str) and candidate.strip():
                    try:
                        candidate_endpoint = json.loads(candidate) or {}
                    except Exception:
                        candidate_endpoint = {}
                else:
                    candidate_endpoint = {}
                if isinstance(candidate_endpoint, dict) and candidate_endpoint.get("instance_id"):
                    instance_id = str(candidate_endpoint["instance_id"])
                    break
    finally:
        db.close()

    if not instance_id:
        raise RuntimeError("instance_id_not_found")

    # Phase 2: stop the instance in AWS.
    stop_instance(instance_id, wait=wait)

    # Phase 3: record the stop event in our DB (best-effort).
    db = SessionLocal()
    try:
        db.execute(
            text(
                """
                UPDATE vm_instances
                SET status = 'stopped',
                    stopped_at = NOW()
                WHERE run_id = :run_id
                """
            ),
            {"run_id": run_id},
        )
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"[workspace_service] Failed to update vm_instances stopped_at for run_id={run_id}: {e}")
    finally:
        db.close()

    return instance_id
