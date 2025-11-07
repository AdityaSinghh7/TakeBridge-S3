from __future__ import annotations

from collections import defaultdict
from typing import Any, ClassVar, Dict, List, Optional

from framework.utils.streaming import emit_event

from .registry import MCP, init_registry, is_registered


class MCPAgent:
    """Central coordinator for MCP tool invocations and response tracking."""

    _current: ClassVar[Optional["MCPAgent"]] = None

    def __init__(self) -> None:
        init_registry()
        self.last_response: Optional[Dict[str, Any]] = None
        self.history: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        self.current_step: Optional[int] = None
        self.last_action_type: Optional[str] = None  # "mcp" or "gui"
        self.current_step_action_type: Optional[str] = None

    @classmethod
    def set_current(cls, agent: "MCPAgent") -> None:
        cls._current = agent

    @classmethod
    def current(cls) -> "MCPAgent":
        if cls._current is None:
            cls._current = MCPAgent()
        return cls._current

    def set_step(self, step_index: Optional[int]) -> None:
        self.current_step = step_index
        self.current_step_action_type = None

    def finalize_step(self) -> None:
        action_type = self.current_step_action_type or "gui"
        self.last_action_type = action_type
        self.current_step_action_type = None

    def _record_response(
        self, provider: str, tool: str, response: Dict[str, Any]
    ) -> None:
        entry = {
            "provider": provider,
            "tool": tool,
            "step": self.current_step,
            "response": response,
        }
        self.last_response = entry
        self.history.setdefault(tool, []).append(entry)

    def call_tool(
        self, provider: str, tool: str, payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Invoke an MCP tool, record telemetry, and persist response history."""
        client = MCP.get(provider)
        if not client or not is_registered(provider):
            emit_event(
                "mcp.call.skipped",
                {"server": provider, "tool": tool, "reason": "unconfigured"},
            )
            raise RuntimeError(f"MCP provider '{provider}' is not configured.")

        emit_event(
            "mcp.call.started",
            {"server": provider, "tool": tool, "step": self.current_step},
        )
        try:
            response = client.call(tool, payload)
        except Exception as exc:
            emit_event(
                "mcp.call.failed",
                {
                    "server": provider,
                    "tool": tool,
                    "step": self.current_step,
                    "error": str(exc),
                },
            )
            raise
        emit_event(
            "mcp.call.completed",
            {
                "server": provider,
                "tool": tool,
                "step": self.current_step,
                "response": response,
            },
        )
        self._record_response(provider, tool, response)
        self.current_step_action_type = "mcp"
        return response
