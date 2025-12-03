from __future__ import annotations

"""
Task composition endpoint.

This route lets clients submit a raw task and receive an editable composed plan
that reflects the user's MCP + computer-use capabilities.
"""

from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, Depends, HTTPException

from orchestrator_agent.capabilities import (
    fetch_mcp_capabilities,
    _normalize_platform,
    fetch_computer_capabilities
)
from orchestrator_agent.composer import compose_plan
from server.api.auth import CurrentUser, get_current_user
from orchestrator_agent.data_types import OrchestratorRequest


router = APIRouter(prefix="/compose_task", tags=["task-compose"])




@router.post("")
async def compose_task(
    payload: Dict[str, Any] = Body(...),
    current_user: CurrentUser = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Compose a multi-step plan for a raw task using current capabilities.

    This endpoint does NOT require a VM connection. It uses:
    - MCP capabilities (authorized providers/tools) - fetched from database
    - Computer capabilities - uses a static list of common apps per platform
      (no VM call needed)

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

    # For planning, we only need MCP capabilities (which don't require a VM).
    # Computer capabilities use a static list of common apps per platform.
    # This makes /compose_task work even when no VM is running or accessible.
    
    # Fetch MCP capabilities (essential for planning)
    mcp_caps = fetch_mcp_capabilities(user_id, force_refresh=False)
    
    # Determine platform - use payload if provided, otherwise default to darwin
    # No need to call VM/workspace - we just need a reasonable default for common apps
    platform_override = payload.get("platform")
    platform = _normalize_platform(platform_override) if platform_override else "darwin"
    
    # Use common apps list instead of calling VM
    # This provides a reasonable set of apps the compose agent can plan with
    common_apps = fetch_computer_capabilities(OrchestratorRequest(task=task, user_id=user_id, platform=platform))
    
    computer_caps = {
        "platform": platform,
        "available_apps": common_apps,
        "active_windows": [],  # Not needed for planning
    }
    
    # Combine capabilities
    capabilities = {
        "mcp": mcp_caps,
        "computer": computer_caps,
    }

    tool_constraints = payload.get("tool_constraints")
    plan = compose_plan(task, capabilities, tool_constraints=tool_constraints)
    return plan


__all__ = ["router"]


