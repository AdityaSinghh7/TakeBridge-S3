"""Adapter between server API and orchestrator_agent.

This module provides conversion functions between the legacy computer_use_agent
request format (OrchestrateRequest) and the new orchestrator_agent format
(OrchestratorRequest). This enables backward compatibility during the transition.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, Optional

from computer_use_agent.orchestrator.data_types import OrchestrateRequest
from orchestrator_agent.data_types import (
    Budget,
    OrchestratorRequest,
    TenantContext,
    ToolConstraints,
)


def orchestrate_to_orchestrator(
    req: OrchestrateRequest,
    *,
    user_id: Optional[str] = None,
    tool_constraints: Optional[Dict[str, Any]] = None,
    workspace: Optional[Dict[str, Any]] = None,
) -> OrchestratorRequest:
    """Convert OrchestrateRequest to OrchestratorRequest.

    Args:
        req: The legacy OrchestrateRequest from computer_use_agent
        user_id: Optional user ID for multi-tenancy
        tool_constraints: Optional tool constraints dict with keys:
            - mode: "auto" | "custom"
            - providers: List[str] (for custom mode)
            - tools: List[str] (for custom mode)
        workspace: Optional workspace context (id, controller_base_url, vnc_url)

    Returns:
        OrchestratorRequest compatible with orchestrator_agent runtime
    """
    # Create tenant context
    tenant = TenantContext(
        tenant_id=user_id or "default",
        request_id=uuid.uuid4().hex,
        user_id=user_id,
    )

    # Create budget
    budget = Budget(
        max_steps=req.worker.max_steps if hasattr(req, "worker") else 15,
    )

    # Parse tool constraints if provided
    tool_constraints_obj: Optional[ToolConstraints] = None
    if tool_constraints:
        tool_constraints_obj = ToolConstraints(
            mode=tool_constraints.get("mode", "auto"),
            providers=tool_constraints.get("providers", []),
            tools=tool_constraints.get("tools", []),
        )

    # Build metadata dict
    metadata: Dict[str, Any] = {
        "controller": {
            "base_url": req.controller.base_url,
            "host": req.controller.host,
            "port": req.controller.port,
            "timeout": req.controller.timeout,
        },
        "worker": {
            "engine_params": req.worker.engine_params,
            "max_steps": req.worker.max_steps,
            "max_trajectory_length": req.worker.max_trajectory_length,
            "enable_reflection": req.worker.enable_reflection,
            "post_action_worker_delay": req.worker.post_action_worker_delay,
        },
        "grounding": {
            "engine_params_for_generation": req.grounding.engine_params_for_generation,
            "engine_params_for_grounding": req.grounding.engine_params_for_grounding,
            "code_agent_engine_params": req.grounding.code_agent_engine_params,
            "code_agent_budget": req.grounding.code_agent_budget,
            "grounding_base_url": req.grounding.grounding_base_url,
            "grounding_system_prompt": req.grounding.grounding_system_prompt,
            "grounding_timeout": req.grounding.grounding_timeout,
            "grounding_max_retries": req.grounding.grounding_max_retries,
            "grounding_api_key": req.grounding.grounding_api_key,
        },
        "platform": req.platform,
    }
    if tool_constraints:
        metadata["tool_constraints_dict"] = tool_constraints
    if workspace:
        metadata["workspace"] = workspace

    # Optional composed plan passed through from the original request payload
    composed_plan = getattr(req, "composed_plan", None)

    return OrchestratorRequest(
        task=req.task,
        max_steps=budget.max_steps,
        tenant=tenant,
        platform=req.platform if hasattr(req, "platform") else None,
        allow_code_execution=(
            req.enable_code_execution
            if hasattr(req, "enable_code_execution")
            else False
        ),
        budget=budget,
        metadata=metadata,
        request_id=tenant.request_id,
        user_id=user_id,
        tool_constraints=tool_constraints_obj,
        composed_plan=composed_plan,
    )


__all__ = ["orchestrate_to_orchestrator"]
