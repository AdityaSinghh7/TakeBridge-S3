from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Dict, Iterator, List, Optional

from computer_use_agent.tools.mcp_proxy import (
    MCPToolBridge,
    ToolCallContext,
    ToolDescription,
)
from computer_use_agent.grounding.grounding_agent import ACI
from computer_use_agent.orchestrator.data_types import ToolConstraints
from mcp_agent.action_registry import sync_registered_actions
from mcp_agent.actions import (
    configure_mcp_action_filters,
    describe_available_actions,
)
from mcp_agent.mcp_agent import MCPAgent  # TODO: Migrate to execute_task from agent.entrypoint
from mcp_agent.user_identity import normalize_user_id, resolve_dev_user_id
from shared.streaming import emit_event


class MCPAgentBridge(MCPToolBridge):
    """Concrete MCP bridge backed by the legacy MCPAgent."""

    def __init__(self, user_id: str | None = None) -> None:
        resolved = normalize_user_id(user_id) if user_id is not None else resolve_dev_user_id()
        self._agent = MCPAgent(resolved)
        MCPAgent.set_current(self._agent)

    def set_step(self, step_index: Optional[int]) -> None:
        self._agent.set_step(step_index)

    def finalize_step(self) -> None:
        self._agent.finalize_step()

    def call_tool(self, context: ToolCallContext) -> Dict[str, Any]:
        return self._agent.call_tool(context.provider, context.tool, context.payload)

    @property
    def last_response(self):
        return self._agent.last_response

    @property
    def last_action_type(self) -> Optional[str]:
        return self._agent.last_action_type

    @property
    def current_step_action_type(self) -> Optional[str]:
        return self._agent.current_step_action_type

    @property
    def history(self):
        return self._agent.history

    def available_actions(self) -> List[ToolDescription]:
        return [
            ToolDescription(
                provider=entry["provider"],
                name=entry["name"],
                doc=entry.get("doc", ""),
            )
            for entry in describe_available_actions(user_id=self._agent.user_id)
        ]


@contextmanager
def configure_mcp_tools(constraints: Optional[ToolConstraints], *, user_id: str | None = None) -> Iterator[None]:
    """Apply tool constraints and synchronize MCP action shims for the run."""
    active_user = normalize_user_id(user_id) if user_id is not None else resolve_dev_user_id()
    providers = None
    tools = None
    mode = "auto"
    if constraints:
        mode = constraints.mode
        if constraints.mode == "custom":
            providers = constraints.providers
            tools = constraints.tools
    configure_mcp_action_filters(providers, tools)
    sync_registered_actions(user_id=active_user, aci_class=ACI)
    emit_event(
        "runner.tools.configured",
        {
            "mode": mode,
            "providers": providers,
            "tools": tools,
        },
    )
    try:
        yield
    finally:
        configure_mcp_action_filters(None, None)
        sync_registered_actions(user_id=active_user, aci_class=ACI)
