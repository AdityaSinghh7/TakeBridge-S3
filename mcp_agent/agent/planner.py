from __future__ import annotations

import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, Optional

from mcp_agent.core.context import AgentContext
from mcp_agent.env_sync import ensure_env_for_provider
from mcp_agent.user_identity import normalize_user_id
from mcp_agent.sandbox.ephemeral import generate_ephemeral_toolbox

from .budget import Budget
from .state import AgentState
from .llm import PlannerLLM
from .orchestrator import AgentOrchestrator
from .types import MCPTaskResult


def execute_mcp_task(
    task: str,
    *,
    user_id: str,
    budget: Budget | None = None,
    extra_context: Dict[str, Any] | None = None,
    llm: PlannerLLM | None = None,
) -> MCPTaskResult:
    """
    Execute a standalone MCP task and return a structured result.

    Args:
        task: Required natural-language request from the user.
        user_id: Required identifier used to scope MCP registry state.
        budget: Optional overrides for step/tool/code/cost ceilings.
        extra_context: Optional dict of metadata accessible to the planner.

    Returns:
        MCPTaskResult: structure containing success, summary, budget usage, logs, and optional error.
    """

    if not isinstance(task, str) or not task.strip():
        raise ValueError("task must be a non-empty string.")
    normalized_user = normalize_user_id(user_id)

    with tempfile.TemporaryDirectory(prefix=f"toolbox-{normalized_user}-") as temp_dir:
        toolbox_path = Path(temp_dir)

        agent_context = AgentContext.create(
            user_id=normalized_user,
            extra={"toolbox_root": str(toolbox_path)},
        )

        generate_ephemeral_toolbox(agent_context, toolbox_path)

        state = AgentState(
            task=task.strip(),
            user_id=normalized_user,
            request_id=agent_context.request_id,
            budget=budget or Budget(),
            extra_context=extra_context or {},
        )
        for provider in ("gmail", "slack"):
            ensure_env_for_provider(normalized_user, provider)
        state.record_event(
            "mcp.planner.started",
            {
                "budget": asdict(state.budget_tracker.snapshot()),
                "extra_context_keys": sorted(state.extra_context.keys()),
                "ephemeral_toolbox": str(toolbox_path),
            },
        )
        runtime = AgentOrchestrator(agent_context, state, llm=llm)
        return runtime.run()


# Backwards compatibility alias until tests/migrants updated
PlannerRuntime = AgentOrchestrator
