from __future__ import annotations

import argparse
import hashlib
import os
import tempfile
from pathlib import PurePosixPath, PureWindowsPath
from typing import Optional, Tuple

import requests

from server.api.controller_client import VMControllerClient
from server.api.drive_utils import build_drive_key, normalize_drive_path
from shared.storage import get_attachment_storage

CHUNK_BYTES = 4 * 1024 * 1024
DRIVE_VM_BASE_PATH = os.path.expanduser(os.getenv("DRIVE_VM_BASE_PATH", "/home/user/session/drive"))


def _download_to_temp(url: str) -> Tuple[tempfile.SpooledTemporaryFile, str, int]:
    tmp = tempfile.SpooledTemporaryFile(max_size=64 * 1024 * 1024)
    hasher = hashlib.sha256()
    size = 0
    with requests.get(url, stream=True, timeout=300) as resp:
        resp.raise_for_status()
        for chunk in resp.iter_content(chunk_size=CHUNK_BYTES):
            if not chunk:
                continue
            tmp.write(chunk)
            hasher.update(chunk)
            size += len(chunk)
    tmp.seek(0)
    return tmp, hasher.hexdigest(), size


def _hash_vm_file(controller: VMControllerClient, path: str) -> Tuple[str, int]:
    hasher = hashlib.sha256()
    size = 0
    with controller.stream_file(path, timeout=300) as resp:
        for chunk in resp.iter_content(chunk_size=CHUNK_BYTES):
            if not chunk:
                continue
            hasher.update(chunk)
            size += len(chunk)
    return hasher.hexdigest(), size


def _is_windows_path(path: str) -> bool:
    return ":" in path or "\\" in path


def _build_drive_vm_path(drive_path: str, *, base_path: str, windows: bool) -> str:
    parts = [part for part in drive_path.split("/") if part]
    if windows:
        return str(PureWindowsPath(base_path, *parts))
    return str(PurePosixPath(base_path, *parts))


def _ensure_vm_dir(controller: VMControllerClient, dest_path: str, *, windows: bool) -> None:
    parent = str(PureWindowsPath(dest_path).parent) if windows else str(PurePosixPath(dest_path).parent)
    if not parent:
        return
    if windows:
        try:
            controller.execute(
                f'powershell -NoProfile -Command "New-Item -ItemType Directory -Force -Path \\"{parent}\\""',
                shell=True,
                setup=True,
            )
        except Exception:
            controller.execute(["cmd", "/c", "mkdir", parent], setup=True)
        return
    controller.execute(["mkdir", "-p", parent], setup=True)


def stage_drive_file(
    *,
    controller_base_url: Optional[str],
    user_id: str,
    drive_path: str,
    r2_key: Optional[str],
) -> None:
    normalized = normalize_drive_path(drive_path)
    key = r2_key or build_drive_key(user_id, normalized)
    storage = get_attachment_storage()
    presigned_url = storage.generate_presigned_get(key)

    print(f"[drive-stage] r2_key={key}")
    tmp, sha, size = _download_to_temp(presigned_url)
    print(f"[drive-stage] downloaded {size} bytes sha256={sha}")

    controller = VMControllerClient(base_url=controller_base_url)
    controller.wait_for_health()
    windows = _is_windows_path(DRIVE_VM_BASE_PATH)
    dest_path = _build_drive_vm_path(normalized, base_path=DRIVE_VM_BASE_PATH, windows=windows)
    _ensure_vm_dir(controller, dest_path, windows=windows)
    controller.upload_file(dest_path, tmp)
    tmp.close()

    vm_sha, vm_size = _hash_vm_file(controller, dest_path)
    print(f"[drive-stage] vm_path={dest_path} size={vm_size} sha256={vm_sha}")
    if vm_sha != sha:
        raise RuntimeError("hash_mismatch_after_upload")
    print("[drive-stage] SUCCESS: file staged to VM and verified")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Stage a Drive file from R2 into the VM and verify checksum.",
    )
    parser.add_argument("--user-id", required=True, help="Supabase user id (JWT sub)")
    parser.add_argument("--drive-path", required=True, help="Drive path (e.g. Documents/a.txt)")
    parser.add_argument(
        "--r2-key",
        default=None,
        help="Explicit R2 key (optional, defaults to <user_id>/drive/<path>)",
    )
    parser.add_argument(
        "--controller-base-url",
        default=None,
        help="VM controller base URL (optional, uses VM_SERVER_* env vars if omitted)",
    )
    args = parser.parse_args()

    stage_drive_file(
        controller_base_url=args.controller_base_url,
        user_id=args.user_id,
        drive_path=args.drive_path,
        r2_key=args.r2_key,
    )


if __name__ == "__main__":
    main()
