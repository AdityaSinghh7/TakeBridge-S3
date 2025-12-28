#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from pathlib import PurePosixPath, PureWindowsPath, Path
from typing import Any, Dict, Optional

import requests

REPO_ROOT = Path(__file__).resolve().parents[1]
import sys

sys.path.append(str(REPO_ROOT))

from server.api.controller_client import VMControllerClient  # noqa: E402
from server.api.run_drive import DRIVE_VM_BASE_PATH, commit_drive_changes_for_run, detect_drive_changes  # noqa: E402
from shared.db.engine import SessionLocal  # noqa: E402
from shared.db import workflow_runs  # noqa: E402


def _get_controller_base_url(run_id: str) -> Optional[str]:
    db = SessionLocal()
    try:
        env = workflow_runs.get_environment(db, run_id=run_id) or {}
    finally:
        db.close()
    endpoint = env.get("endpoint") if isinstance(env, dict) else None
    if isinstance(endpoint, str):
        try:
            endpoint = json.loads(endpoint)
        except Exception:
            endpoint = None
    if isinstance(endpoint, dict):
        return endpoint.get("controller_base_url") or endpoint.get("base_url")
    if isinstance(env, dict):
        return env.get("controller_base_url") or env.get("base_url")
    return None


def _is_windows_path(path: str) -> bool:
    return ":" in path or "\\" in path


def _build_vm_path(base_path: str, drive_path: str, windows: bool) -> str:
    parts = [part for part in drive_path.split("/") if part]
    if windows:
        return str(PureWindowsPath(base_path, *parts))
    return str(PurePosixPath(base_path, *parts))


def _ensure_vm_dir(controller: VMControllerClient, dest_path: str, *, windows: bool) -> None:
    parent = str(PureWindowsPath(dest_path).parent) if windows else str(PurePosixPath(dest_path).parent)
    if not parent:
        return
    if windows:
        controller.execute(
            f'powershell -NoProfile -Command "New-Item -ItemType Directory -Force -Path \\"{parent}\\""',
            shell=True,
            setup=True,
        )
    else:
        controller.execute(["mkdir", "-p", parent], setup=True)


def _write_vm_file(controller: VMControllerClient, path: str, content: str, *, windows: bool, append: bool) -> None:
    safe = content.replace("\\", "\\\\").replace('"', '\\"')
    op = ">>" if append else ">"
    if windows:
        cmd = f'powershell -NoProfile -Command "Add-Content -Path \\"{path}\\" -Value \\"{safe}\\""'
        if not append:
            cmd = f'powershell -NoProfile -Command "Set-Content -Path \\"{path}\\" -Value \\"{safe}\\""'
        controller.execute(cmd, shell=True, setup=True)
    else:
        controller.execute(f'printf "%s" "{safe}" {op} "{path}"', shell=True, setup=True)


def _fetch_drive_summary(
    api_base_url: str,
    run_id: str,
    auth_token: str,
) -> Dict[str, Any]:
    resp = requests.get(
        f"{api_base_url.rstrip('/')}/api/runs/{run_id}/drive-summary",
        headers={"Authorization": f"Bearer {auth_token}"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def main() -> None:
    run_id = os.getenv("RUN_ID", "").strip()
    if not run_id:
        raise SystemExit("RUN_ID is required.")

    controller_base_url = os.getenv("CONTROLLER_BASE_URL", "").strip()
    if not controller_base_url:
        controller_base_url = _get_controller_base_url(run_id) or ""
    if not controller_base_url:
        raise SystemExit("CONTROLLER_BASE_URL is required or must be resolvable from workflow_runs.environment.")

    drive_base = os.getenv("DRIVE_VM_BASE_PATH", DRIVE_VM_BASE_PATH)
    windows = _is_windows_path(drive_base)

    new_drive_path = os.getenv("NEW_DRIVE_PATH", "test/new_file.txt").strip()
    existing_drive_path = os.getenv("EXISTING_DRIVE_PATH", "checker.txt").strip()
    new_content = os.getenv("NEW_FILE_CONTENT", "hello from test\n")
    append_content = os.getenv("APPEND_CONTENT", "\nappended from test\n")

    controller = VMControllerClient(base_url=controller_base_url)
    controller.wait_for_health()

    new_vm_path = _build_vm_path(drive_base, new_drive_path, windows)
    _ensure_vm_dir(controller, new_vm_path, windows=windows)
    _write_vm_file(controller, new_vm_path, new_content, windows=windows, append=False)

    existing_vm_path = _build_vm_path(drive_base, existing_drive_path, windows)
    _ensure_vm_dir(controller, existing_vm_path, windows=windows)
    _write_vm_file(controller, existing_vm_path, append_content, windows=windows, append=True)

    workspace = {"controller_base_url": controller_base_url}
    changes = detect_drive_changes(run_id, workspace)
    committed = commit_drive_changes_for_run(run_id, workspace)

    print(f"Detected changes: {len(changes)}")
    for item in changes:
        print(f"- {item.get('path')} ({item.get('change_type')})")
    print(f"Committed changes: {len(committed)}")
    for item in committed:
        print(f"- {item.get('path')} ({item.get('change_type')}) change={item.get('r2_key')}")

    api_base_url = os.getenv("API_BASE_URL", "").strip()
    auth_token = os.getenv("AUTH_TOKEN", "").strip()
    if api_base_url and auth_token:
        summary = _fetch_drive_summary(api_base_url, run_id, auth_token)
        print("Drive summary:")
        print(json.dumps(summary, indent=2))
    else:
        print("Skipping drive summary fetch (set API_BASE_URL and AUTH_TOKEN to enable).")


if __name__ == "__main__":
    main()
