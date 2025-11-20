from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, Optional, TypedDict

from mcp_agent.core.context import AgentContext
from mcp_agent.env_sync import ensure_env_for_provider
from mcp_agent.user_identity import normalize_user_id

from .budget import Budget
from .state import AgentState
from .llm import PlannerLLM
from .orchestrator import AgentOrchestrator


class MCPTaskResult(TypedDict, total=False):
    success: bool
    final_summary: str
    error: Optional[str]
    error_code: Optional[str]
    error_message: Optional[str]
    error_details: Dict[str, Any]
    user_id: str
    run_id: str
    raw_outputs: Dict[str, Any]
    budget_usage: Dict[str, Any]
    logs: list[Dict[str, Any]]
    steps: list[Dict[str, Any]]


def execute_mcp_task(
    task: str,
    *,
    user_id: str,
    budget: Budget | None = None,
    extra_context: Dict[str, Any] | None = None,
    toolbox_root: Path | None = None,
    llm: PlannerLLM | None = None,
) -> MCPTaskResult:
    """
    Execute a standalone MCP task and return a structured result.

    Args:
        task: Required natural-language request from the user.
        user_id: Required identifier used to scope MCP registry state.
        budget: Optional overrides for step/tool/code/cost ceilings.
        extra_context: Optional dict of metadata accessible to the planner.
        toolbox_root: Optional path to a generated toolbox (defaults to ./toolbox).

    Returns:
        MCPTaskResult: structure containing success, summary, budget usage, logs, and optional error.
    """

    if not isinstance(task, str) or not task.strip():
        raise ValueError("task must be a non-empty string.")
    normalized_user = normalize_user_id(user_id)
    resolved_toolbox = Path(toolbox_root).resolve() if toolbox_root else Path("toolbox").resolve()

    agent_context = AgentContext.create(
        user_id=normalized_user,
        extra={"toolbox_root": str(resolved_toolbox)},
    )
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
        },
    )
    runtime = AgentOrchestrator(agent_context, state, llm=llm)
    return runtime.run()


# Backwards compatibility alias until tests/migrants updated
PlannerRuntime = AgentOrchestrator
