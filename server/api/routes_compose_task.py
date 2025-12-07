from __future__ import annotations

"""
Task composition endpoint.

This route lets clients submit a raw task and receive an editable composed plan
that reflects the user's MCP + computer-use capabilities.
"""

import logging
import uuid
from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, Depends, HTTPException

from orchestrator_agent.capabilities import (
    fetch_mcp_capabilities,
    fetch_computer_capabilities,
    _normalize_platform,
)
from orchestrator_agent.composer import compose_plan
from orchestrator_agent.data_types import OrchestratorRequest
from server.api.auth import CurrentUser, get_current_user

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

    controller_metadata: Dict[str, Any] = {}

    capability_request = OrchestratorRequest.from_task(
        tenant_id=user_id,
        task=task,
        max_steps=1,
        metadata={"controller": controller_metadata},
        platform=platform,
        user_id=user_id,
    )

    # Computer capabilities (with fallback when controller is unavailable)
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
    draft_id = str(uuid.uuid4())
    suggested_name = payload.get("name") or task[:80]
    suggested_description = payload.get("description")

    return {
        "plan": plan,
        "suggested_name": suggested_name,
        "suggested_description": suggested_description,
        "draft_id": draft_id,
    }


__all__ = ["router"]
