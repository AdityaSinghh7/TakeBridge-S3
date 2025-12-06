from __future__ import annotations

"""
Task composition endpoint.

This route lets clients submit a raw task and receive an editable composed plan
that reflects the user's MCP + computer-use capabilities.
"""

import logging
import uuid
from typing import Any, Dict, Optional
from urllib.parse import urlparse

from fastapi import APIRouter, Body, Depends, HTTPException

from orchestrator_agent.capabilities import (
    fetch_mcp_capabilities,
    _normalize_platform,
    fetch_computer_capabilities,
)
from orchestrator_agent.composer import compose_plan
from orchestrator_agent.data_types import OrchestratorRequest
from server.api.auth import CurrentUser, get_current_user
from vm_manager.vm_wrapper import ensure_workspace
from vm_manager.config import settings
from shared.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/compose_task", tags=["task-compose"])




@router.post("")
async def compose_task(
    payload: Dict[str, Any] = Body(...),
    current_user: CurrentUser = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Compose a multi-step plan for a raw task using current capabilities.

    It uses:
    - MCP capabilities (authorized providers/tools) - fetched from database
    - Computer capabilities - fetched from the per-user VM when available

    Request body:
      - task: str (required) – raw user task description
      - tool_constraints: Optional[dict] – forwarded to compose_plan for context
      - platform: Optional[str] – platform hint ("darwin", "windows", "linux")
        defaults to "darwin" if not provided

    Response:
      - ComposedPlan JSON object (schema_version=1) suitable for user editing.
    """
    task = (payload.get("task") or "").strip()
    if not task:
        raise HTTPException(status_code=400, detail="Field 'task' is required and must be non-empty.")

    user_id: str = current_user.sub
    
    logger.info(f"/compose_task endpoint called - user_id={user_id}, task={task[:100]}...")

    # Fetch MCP capabilities (essential for planning)
    mcp_caps = fetch_mcp_capabilities(user_id, force_refresh=False)

    # Optional platform hint; actual platform will come from the VM when available
    platform_override = payload.get("platform")
    platform = _normalize_platform(platform_override) if platform_override else None

    # Ensure we have a per-user workspace and derive controller connection details
    workspace = ensure_workspace(user_id)
    base_url = workspace.controller_base_url
    if not base_url:
        raise HTTPException(
            status_code=500,
            detail="Workspace controller_base_url is missing for compose_task",
        )

    parsed = urlparse(base_url)
    host = parsed.hostname if parsed else None
    port = parsed.port or settings.AGENT_CONTROLLER_PORT

    controller_metadata = {
        "base_url": base_url,
        "host": host,
        "port": port,
        # timeout is optional; VMControllerClient will use its default if omitted
    }

    capability_request = OrchestratorRequest.from_task(
        tenant_id=user_id,
        task=task,
        max_steps=1,
        metadata={"controller": controller_metadata},
        platform=platform,
        user_id=user_id,
    )

    # Fetch live computer capabilities (platform, available apps, active windows)
    computer_caps = fetch_computer_capabilities(capability_request, force_refresh=False)

    # Combine capabilities
    capabilities = {
        "mcp": mcp_caps,
        "computer": computer_caps,
    }

    tool_constraints = payload.get("tool_constraints")
    logger.info(f"Calling compose_plan for task: {task[:100]}...")
    plan = compose_plan(task, capabilities, tool_constraints=tool_constraints)
    logger.info(f"compose_plan completed - returned plan with {len(plan.get('steps', []))} steps, schema_version={plan.get('schema_version')}")
    # Persist/update workflow in Supabase
    client = get_supabase_client(current_user.token)
    workflow_id = payload.get("workflow_id") or str(uuid.uuid4())
    folder_id = payload.get("folder_id")
    workflow_name = payload.get("name") or task[:80]
    workflow_description = payload.get("description")

    status_value = "active"
    try:
        existing = client.table("workflows").select("status").eq("id", workflow_id).single().execute()
        if existing.data and existing.data.get("status"):
            status_value = existing.data["status"]
    except Exception:
        status_value = "active"

    upsert_payload = {
        "id": workflow_id,
        "user_id": user_id,
        "folder_id": folder_id,
        "name": workflow_name,
        "prompt": task,
        "description": workflow_description,
        "definition_json": plan,
        "status": status_value,
    }

    try:
        client.table("workflows").upsert(upsert_payload, on_conflict="id").execute()
    except Exception as exc:
        logger.exception("Failed to upsert workflow in Supabase: %s", exc)
        raise HTTPException(status_code=500, detail="failed_to_save_workflow")

    plan_with_id = {**plan, "workflow_id": workflow_id, "folder_id": folder_id}
    return plan_with_id


__all__ = ["router"]

