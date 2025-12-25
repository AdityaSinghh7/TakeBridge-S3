from __future__ import annotations

import logging
import posixpath
from datetime import datetime
from typing import Any, Dict, Optional

from botocore.exceptions import ClientError
from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel, Field

from server.api.auth import CurrentUser, get_current_user
from server.api.drive_utils import build_drive_key, build_drive_prefix, normalize_drive_path
from shared.storage import get_attachment_storage, AttachmentStorageError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/drive", tags=["drive"])

DEFAULT_CONTENT_TYPE = "application/octet-stream"


class DriveUploadRequest(BaseModel):
    path: str = Field(..., max_length=1024)
    content_type: Optional[str] = None
    size: Optional[int] = Field(default=None, ge=0)


class DriveDeleteRequest(BaseModel):
    path: str = Field(..., max_length=1024)


class DriveRenameRequest(BaseModel):
    from_path: str = Field(..., max_length=1024)
    to_path: str = Field(..., max_length=1024)


@router.get("/list")
def list_drive(
    prefix: Optional[str] = None,
    delimiter: str = "/",
    current_user: CurrentUser = Depends(get_current_user),
) -> Dict[str, Any]:
    try:
        normalized_prefix = normalize_drive_path(
            prefix or "",
            allow_empty=True,
            allow_trailing_slash=True,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    try:
        storage = get_attachment_storage()
    except AttachmentStorageError as exc:
        logger.error("Drive storage misconfigured: %s", exc)
        raise HTTPException(status_code=500, detail="attachments_not_configured")

    base_prefix = build_drive_key(current_user.sub, "")
    list_prefix = build_drive_prefix(current_user.sub, normalized_prefix)

    try:
        resp = storage.list_objects(prefix=list_prefix, delimiter=delimiter or "/")
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code")
        if code in {"NoSuchKey", "404"}:
            return {"prefix": normalized_prefix, "items": []}
        logger.warning("Drive list failed prefix=%s: %s", list_prefix, exc)
        raise HTTPException(status_code=500, detail="drive_list_failed")

    items = []
    for entry in resp.get("CommonPrefixes") or []:
        full_prefix = entry.get("Prefix")
        if not full_prefix or not full_prefix.startswith(base_prefix):
            continue
        rel = full_prefix[len(base_prefix) :]
        if not rel:
            continue
        name = rel.rstrip("/").split("/")[-1]
        items.append({"type": "folder", "path": rel, "name": name})

    for entry in resp.get("Contents") or []:
        key = entry.get("Key")
        if not key or not key.startswith(base_prefix):
            continue
        rel = key[len(base_prefix) :]
        if not rel or rel.endswith("/"):
            continue
        name = posixpath.basename(rel)
        last_modified = entry.get("LastModified")
        if isinstance(last_modified, datetime):
            last_modified = last_modified.isoformat()
        etag = (entry.get("ETag") or "").strip('"') or None
        items.append(
            {
                "type": "file",
                "path": rel,
                "name": name,
                "size": entry.get("Size"),
                "last_modified": last_modified,
                "etag": etag,
            }
        )

    return {"prefix": normalized_prefix, "items": items}


@router.post("/request-upload")
def request_drive_upload(
    payload: DriveUploadRequest = Body(...),
    current_user: CurrentUser = Depends(get_current_user),
) -> Dict[str, Any]:
    try:
        drive_path = normalize_drive_path(payload.path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    try:
        storage = get_attachment_storage()
    except AttachmentStorageError as exc:
        logger.error("Drive storage misconfigured: %s", exc)
        raise HTTPException(status_code=500, detail="attachments_not_configured")

    content_type = payload.content_type or DEFAULT_CONTENT_TYPE
    r2_key = build_drive_key(current_user.sub, drive_path)
    presigned_put_url = storage.generate_presigned_put(r2_key, content_type=content_type)

    return {"r2_key": r2_key, "presigned_put_url": presigned_put_url}


@router.get("/request-download")
def request_drive_download(
    path: str,
    current_user: CurrentUser = Depends(get_current_user),
) -> Dict[str, Any]:
    try:
        drive_path = normalize_drive_path(path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    try:
        storage = get_attachment_storage()
    except AttachmentStorageError as exc:
        logger.error("Drive storage misconfigured: %s", exc)
        raise HTTPException(status_code=500, detail="attachments_not_configured")

    r2_key = build_drive_key(current_user.sub, drive_path)
    metadata: Dict[str, Any] = {}
    try:
        head = storage.head_object(r2_key)
        metadata["etag"] = (head.get("ETag") or "").strip('"') or None
        metadata["size"] = head.get("ContentLength")
        last_modified = head.get("LastModified")
        if isinstance(last_modified, datetime):
            metadata["last_modified"] = last_modified.isoformat()
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code")
        if code in {"404", "NoSuchKey"}:
            raise HTTPException(status_code=404, detail="drive_file_not_found") from exc
        raise

    return {
        "r2_key": r2_key,
        "presigned_get_url": storage.generate_presigned_get(r2_key),
        **{k: v for k, v in metadata.items() if v is not None},
    }


@router.post("/delete")
def delete_drive_file(
    payload: DriveDeleteRequest = Body(...),
    current_user: CurrentUser = Depends(get_current_user),
) -> Dict[str, Any]:
    try:
        drive_path = normalize_drive_path(payload.path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    try:
        storage = get_attachment_storage()
    except AttachmentStorageError as exc:
        logger.error("Drive storage misconfigured: %s", exc)
        raise HTTPException(status_code=500, detail="attachments_not_configured")

    r2_key = build_drive_key(current_user.sub, drive_path)
    storage.delete_object(r2_key)
    return {"deleted": True}


@router.post("/rename")
def rename_drive_file(
    payload: DriveRenameRequest = Body(...),
    current_user: CurrentUser = Depends(get_current_user),
) -> Dict[str, Any]:
    try:
        from_path = normalize_drive_path(payload.from_path)
        to_path = normalize_drive_path(payload.to_path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    try:
        storage = get_attachment_storage()
    except AttachmentStorageError as exc:
        logger.error("Drive storage misconfigured: %s", exc)
        raise HTTPException(status_code=500, detail="attachments_not_configured")

    source_key = build_drive_key(current_user.sub, from_path)
    dest_key = build_drive_key(current_user.sub, to_path)
    try:
        storage.copy_object(source_key, dest_key)
        storage.delete_object(source_key)
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code")
        if code in {"404", "NoSuchKey"}:
            raise HTTPException(status_code=404, detail="drive_file_not_found") from exc
        raise

    return {"renamed": True, "from": from_path, "to": to_path}


__all__ = ["router"]
