from __future__ import annotations

import json
import logging
import mimetypes
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List

from sqlalchemy import text

from server.api.controller_client import VMControllerClient
from shared.db.engine import SessionLocal
from shared.storage import get_attachment_storage
from shared.db.models import WorkflowRunArtifact
from .run_attachments import ATTACHMENT_VM_BASE_PATH

logger = logging.getLogger(__name__)

MAX_ARTIFACT_BYTES = int(os.getenv("RUN_ARTIFACT_MAX_BYTES", str(500 * 1024 * 1024)))


def _list_context_entries(controller: VMControllerClient) -> List[Dict[str, Any]]:
    try:
        resp = controller.list_directory(ATTACHMENT_VM_BASE_PATH)
    except Exception as exc:
        logger.warning("list_directory failed for %s: %s", ATTACHMENT_VM_BASE_PATH, exc)
        raise
    entries = resp.get("entries") or []
    flattened: List[Dict[str, Any]] = []
    for entry in entries:
        if entry.get("is_dir"):
            continue
        path = entry.get("path") or os.path.join(ATTACHMENT_VM_BASE_PATH, entry.get("name", ""))
        flattened.append(
            {
                "name": os.path.basename(path),
                "path": path,
                "size": int(entry.get("size") or 0),
                "modified": float(entry.get("modified") or 0.0),
            }
        )
    return flattened


def capture_context_baseline(run_id: str, workspace: Dict[str, Any]) -> None:
    controller_url = workspace.get("controller_base_url")
    if not run_id or not controller_url:
        return
    controller = VMControllerClient(base_url=controller_url)
    try:
        entries = _list_context_entries(controller)
    except Exception:
        return
    baseline = {
        entry["name"]: {"size": entry["size"], "modified": entry["modified"]}
        for entry in entries
    }
    merge_run_environment(run_id, {"context_baseline": baseline})


def export_context_artifacts(run_id: str, workspace: Dict[str, Any]) -> List[Dict[str, Any]]:
    controller_url = workspace.get("controller_base_url")
    if not run_id or not controller_url:
        return []

    env = _get_run_environment(run_id)
    baseline = env.get("context_baseline") or {}

    controller = VMControllerClient(base_url=controller_url)
    try:
        entries = _list_context_entries(controller)
    except Exception:
        return []

    logger.info("[artifacts] detected %s entries in context: %s", len(entries), entries)
    changed = []
    for entry in entries:
        prev = baseline.get(entry["name"])
        if not prev or prev.get("size") != entry["size"] or prev.get("modified") != entry["modified"]:
            changed.append(entry)
    if not changed:
        return []

    storage = get_attachment_storage()
    db = SessionLocal()
    exported: List[Dict[str, Any]] = []
    try:
        for entry in changed:
            if entry["size"] > MAX_ARTIFACT_BYTES:
                logger.warning(
                    "Skipping artifact %s (%s bytes) exceeding limit",
                    entry["name"],
                    entry["size"],
                )
                continue
            try:
                data = controller.fetch_file(entry["path"])
            except Exception as exc:
                logger.warning("Failed to fetch artifact %s: %s", entry["path"], exc)
                continue

            key = f"runs/{run_id}/artifacts/{entry['name']}"
            content_type = mimetypes.guess_type(entry["name"])[0]
            try:
                storage.upload_bytes(key, data, content_type=content_type or "application/octet-stream")
            except Exception as exc:
                logger.warning("Failed to upload artifact %s: %s", entry["name"], exc)
                continue

            db.execute(
                text(
                    """
                    DELETE FROM workflow_run_artifacts
                    WHERE run_id = :run_id AND filename = :filename
                    """
                ),
                {"run_id": run_id, "filename": entry["name"]},
            )
            artifact = WorkflowRunArtifact(
                id=str(uuid.uuid4()),
                run_id=run_id,
                filename=entry["name"],
                storage_key=key,
                size_bytes=len(data),
                content_type=content_type,
                source_path=entry["path"],
                metadata_json={},
            )
            db.add(artifact)
            exported.append(
                {
                    "id": artifact.id,
                    "filename": artifact.filename,
                    "size_bytes": artifact.size_bytes,
                    "content_type": artifact.content_type,
                }
            )
        db.commit()
        return exported
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
    return exported


def _get_run_environment(run_id: str) -> Dict[str, Any]:
    db = SessionLocal()
    try:
        row = db.execute(
            text("SELECT environment FROM workflow_runs WHERE id = :run_id"),
            {"run_id": run_id},
        ).scalar_one_or_none()
        if not row:
            return {}
        if isinstance(row, dict):
            return row
        try:
            return json.loads(row)
        except Exception:
            return {}
    finally:
        db.close()


def merge_run_environment(run_id: str, patch: Dict[str, Any]) -> None:
    db = SessionLocal()
    try:
        row = db.execute(
            text("SELECT environment FROM workflow_runs WHERE id = :run_id"),
            {"run_id": run_id},
        ).scalar_one_or_none()
        env: Dict[str, Any]
        if not row:
            env = {}
        elif isinstance(row, dict):
            env = dict(row)
        else:
            try:
                env = json.loads(row) or {}
            except Exception:
                env = {}
        env.update(patch)
        db.execute(
            text(
                """
                UPDATE workflow_runs
                SET environment = :env,
                    updated_at = NOW()
                WHERE id = :run_id
                """
            ),
            {"env": json.dumps(env), "run_id": run_id},
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
