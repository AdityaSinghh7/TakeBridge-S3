from __future__ import annotations

"""
Agent bridges that call MCP and computer-use agents, returning only self-contained
markdown trajectories.

CRITICAL CHANGE: Bridges now return ONLY trajectory_md strings, not raw results.
The trajectory contains all necessary data - no raw outputs are sent to orchestrator.

These bridges are intentionally thin and catch failures to keep the orchestrator
resilient in environments where downstream agents are not fully wired.
"""

import logging
from typing import Any, Dict

from orchestrator_agent.data_types import AgentTarget, OrchestratorRequest, PlannedStep
from shared.hierarchical_logger import set_step_id

logger = logging.getLogger(__name__)


def _build_controller_payload(metadata: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize controller metadata into the config shape expected by the
    computer-use agent. Supports either a VMControllerClient instance or
    a plain dict containing base_url/host/port/timeout.
    """
    try:
        from server.api.controller_client import VMControllerClient  # Late import to avoid hard dependency
    except Exception:  # pragma: no cover - optional dependency
        VMControllerClient = None  # type: ignore

    controller_client = metadata.get("controller_client")
    controller_meta = metadata.get("controller")

    if VMControllerClient and isinstance(controller_client, VMControllerClient):
        return {
            "base_url": controller_client.base_url,
            "host": controller_client.host,
            "port": controller_client.port,
            "timeout": controller_client.timeout,
        }

    if VMControllerClient and isinstance(controller_meta, VMControllerClient):
        return {
            "base_url": controller_meta.base_url,
            "host": controller_meta.host,
            "port": controller_meta.port,
            "timeout": controller_meta.timeout,
        }

    if isinstance(controller_meta, dict):
        return dict(controller_meta)

    return {}


def _extract_mcp_trajectory(raw_result: Dict[str, Any]) -> str:
    """Extract markdown trajectory from MCP agent result.

    IMPORTANT: Only trajectory_md is returned. NO raw outputs.
    The trajectory is self-contained with all data.
    """
    # Try to get the new trajectory_md field
    trajectory_md = raw_result.get("trajectory_md", "")

    if trajectory_md:
        return trajectory_md

    # Fallback for backward compatibility (legacy format without trajectory_md)
    # This preserves old behavior during migration
    logs = raw_result.get("logs") or []
    steps = raw_result.get("steps") or []
    messages = []

    for entry in logs:
        text = entry.get("message") or entry.get("text")
        if text:
            messages.append(str(text))

    for step in steps:
        desc = step.get("description") or step.get("action") or step.get("type")
        outcome = step.get("result") or step.get("outcome") or step.get("observation")
        if desc:
            messages.append(str(desc))
        if outcome:
            messages.append(str(outcome))

    return "\n".join(messages) if messages else "No trajectory available"


def _extract_computer_use_trajectory(raw_result: Dict[str, Any]) -> str:
    """Extract markdown trajectory from computer-use agent result.

    IMPORTANT: Only trajectory_md is returned. NO raw outputs.
    The trajectory is self-contained with all data.
    """
    # Try to get the new trajectory_md field
    trajectory_md = raw_result.get("trajectory_md", "")

    if trajectory_md:
        return trajectory_md

    # Fallback for backward compatibility (legacy format without trajectory_md)
    # This preserves old behavior during migration
    steps = raw_result.get("steps") or []
    messages = []

    for step in steps:
        if not isinstance(step, dict):
            # Attempt to coerce objects to dict for safety
            step = step.__dict__ if hasattr(step, "__dict__") else {}

        plan = step.get("plan") or step.get("action")
        result = step.get("execution_result") or step.get("result")
        reflection = step.get("reflection") or step.get("notes")

        if plan:
            messages.append(str(plan))
        if result:
            messages.append(str(result))
        if reflection:
            messages.append(str(reflection))

    return "\n".join(messages) if messages else "No trajectory available"


def run_mcp_agent(
    request: OrchestratorRequest,
    step: PlannedStep,
) -> str:
    """Execute MCP agent and return self-contained trajectory.

    IMPORTANT: Returns ONLY trajectory string, not raw_result.
    The trajectory contains all necessary data.
    """
    # Bind step_id to context for hierarchical logging
    set_step_id(step.step_id)

    user_id_val = request.user_id or (request.tenant.user_id if request.tenant else None)
    user_id_str = str(user_id_val) if user_id_val is not None else "orchestrator"

    logger.info(
        "bridge.mcp.start task=%s user_id=%s step=%s",
        step.next_task,
        user_id_str,
        step.step_id,
    )
    try:
        from mcp_agent.agent import execute_mcp_task

        # Extract tool constraints and pass in extra_context
        tool_constraints = None
        if request.tool_constraints:
            tool_constraints = request.tool_constraints.to_dict()

        # Build extra_context with step_id and tool_constraints
        extra_context = {
            "request_id": request.request_id,
            "step_id": step.step_id,
            "tool_constraints": tool_constraints,
        }

        raw_result = execute_mcp_task(
            step.next_task,
            user_id=user_id_str,
            budget=None,
            extra_context=extra_context,
        )
        raw_dict = dict(raw_result)
    except Exception as exc:  # pragma: no cover
        logger.info("MCP agent fallback due to error: %s", exc)
        raw_dict = {
            "success": True,
            "final_summary": "MCP agent stubbed output.",
            "error": None,
            "steps": [],
            "logs": [],
            "trajectory_md": "### Error\n**Message**: MCP agent failed to execute\n**Details**: " + str(exc),
        }

    trajectory = _extract_mcp_trajectory(raw_dict)
    logger.info(
        "bridge.mcp.done success=%s steps=%s trajectory_length=%s",
        raw_dict.get("success"),
        len(raw_dict.get("steps") or []),
        len(trajectory),
    )
    return trajectory


def run_computer_use_agent(
    request: OrchestratorRequest,
    step: PlannedStep,
) -> str:
    """Execute computer-use agent and return self-contained trajectory.

    IMPORTANT: Returns ONLY trajectory string, not raw_result.
    The trajectory contains all necessary data.
    """
    # Bind step_id to context for hierarchical logging
    set_step_id(step.step_id)

    try:
        from computer_use_agent.orchestrator.runner import runner
        from computer_use_agent.orchestrator.data_types import OrchestrateRequest

        # Map the orchestrator request into the computer_use_agent shape.
        controller_payload = _build_controller_payload(request.metadata)
        cu_request = OrchestrateRequest.from_dict(
            {
                "task": step.next_task,
                "worker": request.metadata.get("worker") or {},
                "grounding": request.metadata.get("grounding") or {},
                "controller": controller_payload,
                "platform": request.metadata.get("platform"),
                "enable_code_execution": request.allow_code_execution,
            }
        )
        raw_result_obj = runner(cu_request)
        raw_dict = raw_result_obj.__dict__ if hasattr(raw_result_obj, "__dict__") else dict(raw_result_obj)
    except Exception as exc:  # pragma: no cover
        logger.info("Computer-use agent fallback due to error: %s", exc)
        raw_dict = {
            "task": step.next_task,
            "status": "failed",
            "completion_reason": "error",
            "steps": [],
            "grounding_prompts": {},
            "error": str(exc),
            "trajectory_md": "### Error\n**Message**: Computer-use agent failed to execute\n**Details**: " + str(exc),
        }

    trajectory = _extract_computer_use_trajectory(raw_dict)
    logger.info(
        "bridge.computer_use.done status=%s steps=%s trajectory_length=%s",
        raw_dict.get("status"),
        len(raw_dict.get("steps") or []),
        len(trajectory),
    )
    return trajectory


def run_agent_bridge(
    target: AgentTarget,
    request: OrchestratorRequest,
    step: PlannedStep,
) -> str:
    """Execute agent bridge and return self-contained trajectory.

    IMPORTANT: Returns ONLY trajectory string, not raw_result.
    The trajectory contains all necessary data.
    """
    if target == "mcp":
        return run_mcp_agent(request, step)
    if target == "computer_use":
        return run_computer_use_agent(request, step)
    raise ValueError(f"Unsupported agent target: {target}")


__all__ = ["run_agent_bridge", "run_mcp_agent", "run_computer_use_agent"]
