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
) -> OrchestratorRequest:
    """Convert OrchestrateRequest to OrchestratorRequest.

    Args:
        req: The legacy OrchestrateRequest from computer_use_agent
        user_id: Optional user ID for multi-tenancy
        tool_constraints: Optional tool constraints dict with keys:
            - mode: "auto" | "custom"
            - providers: List[str] (for custom mode)
            - tools: List[str] (for custom mode)

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
    metadata: Dict[str, Any] = {}
    if tool_constraints:
        metadata["tool_constraints_dict"] = tool_constraints

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
    )


__all__ = ["orchestrate_to_orchestrator"]
