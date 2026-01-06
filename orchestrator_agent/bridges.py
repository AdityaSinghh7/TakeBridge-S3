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
from dataclasses import asdict, is_dataclass
from typing import Any, Dict, Optional

from orchestrator_agent.data_types import AgentTarget, OrchestratorRequest, PlannedStep
from computer_use_agent.orchestrator.data_types import OrchestrateRequest
from shared.hierarchical_logger import set_step_id

logger = logging.getLogger(__name__)

def _serialize_runner_result(raw_result_obj: Any) -> Dict[str, Any]:
    if raw_result_obj is None:
        return {}
    if is_dataclass(raw_result_obj):
        return asdict(raw_result_obj)
    raw_dict = (
        raw_result_obj.__dict__
        if hasattr(raw_result_obj, "__dict__")
        else dict(raw_result_obj)
    )
    steps = raw_dict.get("steps")
    if isinstance(steps, list):
        raw_dict["steps"] = [
            asdict(step) if is_dataclass(step) else step for step in steps
        ]
    return raw_dict


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
        
        # Persist MCP state to agent_states for handback support
        run_id = request.request_id
        mcp_state_dict = raw_dict.get("state_dict")
        if run_id and mcp_state_dict:
            try:
                from shared.db.workflow_runs import merge_agent_states
                merge_agent_states(run_id, mcp_state_dict, path=["agents", "mcp"])
                logger.info("Persisted MCP state for run_id=%s", run_id)
            except Exception as e:
                logger.warning("Failed to persist MCP state: %s", e)
        
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
    orchestrator_state: Optional[Dict[str, Any]] = None,
) -> str:
    """Execute computer-use agent and return self-contained trajectory.

    IMPORTANT: Returns ONLY trajectory string, not raw_result.
    The trajectory contains all necessary data.
    
    Args:
        request: The orchestrator request
        step: The planned step to execute
        orchestrator_state: Optional serialized orchestrator RunState for handback snapshots
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
        
        # Pass orchestrator state; handback inference is embedded in trajectory snapshots
        runner_metadata = {
            "orchestrator_state": orchestrator_state,
        }
        
        raw_result_obj = runner(cu_request, orchestrator_context=runner_metadata)
        raw_dict = _serialize_runner_result(raw_result_obj)
        
        # Check if this was a handback - if so, raise exception to stop the orchestrator loop
        if raw_dict.get("status") == "attention" and raw_dict.get("completion_reason") == "HANDOFF_TO_HUMAN":
            from orchestrator_agent.exceptions import HandbackRequested
            raise HandbackRequested(
                request=raw_dict.get("handback_request") or "Human intervention required",
                run_id=request.request_id or "",
            )
    except Exception as exc:  # pragma: no cover
        # Re-raise HandbackRequested so it propagates to the orchestrator
        from orchestrator_agent.exceptions import HandbackRequested
        if isinstance(exc, HandbackRequested):
            raise
        
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


def run_computer_use_agent_resume(
    *,
    run_id: Optional[str] = None,
    inference_update: Optional[Dict[str, Any]] = None,
    cu_request: Optional[OrchestrateRequest] = None,
    orchestrator_state: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Execute computer-use agent for a resume flow (post handback) and return trajectory plus raw result.

    Args:
        cu_request: Pre-built OrchestrateRequest to execute
        orchestrator_state: Optional orchestrator state to persist alongside CU snapshot
    resume_state: Prior computer_use snapshot (steps, handback metadata)
    """
    # Bind step_id to context for hierarchical logging
    set_step_id("resume-cu")

    if cu_request is None:
        logger.info(
            "computer_use resume skipped: no cu_request provided (run_id=%s, inference_update_present=%s)",
            run_id,
            bool(inference_update),
        )
        return "Resume not executed; cu_request missing."

    try:
        from computer_use_agent.orchestrator.runner import runner

        runner_metadata = {
            "inference_update": inference_update,
            "is_resume_flow": True,
            "orchestrator_state": orchestrator_state,
        }

        raw_result_obj = runner(cu_request, orchestrator_context=runner_metadata)
        raw_dict = _serialize_runner_result(raw_result_obj)
    except Exception as exc:  # pragma: no cover
        logger.info("Computer-use agent resume fallback due to error: %s", exc)
        raw_dict = {
            "task": cu_request.task if cu_request else "",
            "status": "failed",
            "completion_reason": "error",
            "steps": [],
            "grounding_prompts": {},
            "error": str(exc),
            "trajectory_md": "### Error\n**Message**: Computer-use agent resume failed to execute\n**Details**: " + str(exc),
        }

    trajectory = _extract_computer_use_trajectory(raw_dict)
    logger.info(
        "bridge.computer_use.resume.done status=%s steps=%s trajectory_length=%s",
        raw_dict.get("status"),
        len(raw_dict.get("steps") or []),
        len(trajectory),
    )
    return trajectory, raw_dict


def run_agent_bridge(
    target: AgentTarget,
    request: OrchestratorRequest,
    step: PlannedStep,
    orchestrator_state: Optional[Dict[str, Any]] = None,
) -> str:
    """Execute agent bridge and return self-contained trajectory.

    IMPORTANT: Returns ONLY trajectory string, not raw_result.
    The trajectory contains all necessary data.
    
    Args:
        target: Which agent to execute ("mcp" or "computer_use")
        request: The orchestrator request
        step: The planned step to execute
        orchestrator_state: Optional serialized orchestrator RunState for handback snapshots
    """
    if target == "mcp":
        return run_mcp_agent(request, step)
    if target == "computer_use":
        return run_computer_use_agent(request, step, orchestrator_state=orchestrator_state)
    raise ValueError(f"Unsupported agent target: {target}")


__all__ = ["run_agent_bridge", "run_mcp_agent", "run_computer_use_agent"]
