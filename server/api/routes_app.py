# server/api/routes_app.py

from fastapi import APIRouter, Depends

from .auth import get_current_user, CurrentUser
from server.schemas import RunTaskRequest, RunnerResult
from server.core.orchestrator_client import OrchestratorClient
from server.core.workspace_service import ensure_workspace

router = APIRouter(prefix="/app", tags=["app"])


@router.post("/run_task", response_model=RunnerResult)
async def run_task(
    req: RunTaskRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Run a task on the user's workspace.

    - Resolve / create a workspace for the authenticated user
    - Use its controller_base_url to call the orchestrator

    Authentication: Requires a valid Supabase JWT token in the Authorization header.
    The user_id is extracted from the token (sub claim), ensuring the same user
    across web app, widget, and other clients gets the same workspace.
    """
    user_id = current_user.sub

    # Get or create a workspace row in Supabase
    ws = ensure_workspace(user_id)
    controller_base_url = ws.controller_base_url

    orchestrate_payload = {
        "task": req.task,
        "controller": {
            "base_url": controller_base_url,
            "host": None,
            "port": None,
            "timeout": 30.0,
        },
        "worker": {},  # let orchestrator defaults apply
        "grounding": {},
        "platform": None,
        "enable_code_execution": False,
        "tool_constraints": None,
    }

    client = OrchestratorClient()
    try:
        result = await client.orchestrate(orchestrate_payload)
        return result
    finally:
        await client.close()

