from __future__ import annotations

from collections import defaultdict
from typing import Any, ClassVar, Dict, List, Optional

from shared.streaming import emit_event

from .registry import get_client, init_registry, is_registered


def _normalize_user_id(user_id: str | None) -> str:
    return (user_id or "singleton").strip() or "singleton"


class MCPAgent:
    """Central coordinator for MCP tool invocations and response tracking."""

    _current_by_user: ClassVar[Dict[str, "MCPAgent"]] = {}

    def __init__(self, user_id: str | None = None) -> None:
        self.user_id = _normalize_user_id(user_id)
        init_registry(self.user_id)
        self.last_response: Optional[Dict[str, Any]] = None
        self.history: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        self.current_step: Optional[int] = None
        self.last_action_type: Optional[str] = None  # "mcp" or "gui"
        self.current_step_action_type: Optional[str] = None

    @classmethod
    def set_current(cls, agent: "MCPAgent") -> None:
        cls._current_by_user[agent.user_id] = agent

    @classmethod
    def current(cls, user_id: str | None = None) -> "MCPAgent":
        normalized = _normalize_user_id(user_id)
        agent = cls._current_by_user.get(normalized)
        if agent is None:
            agent = MCPAgent(user_id=normalized)
            cls._current_by_user[normalized] = agent
        return agent

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
            "user_id": self.user_id,
            "response": response,
        }
        self.last_response = entry
        self.history.setdefault(tool, []).append(entry)

    def call_tool(
        self, provider: str, tool: str, payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Invoke an MCP tool, record telemetry, and persist response history."""
        client = get_client(provider, self.user_id)
        if not client or not is_registered(provider, self.user_id):
            emit_event(
                "mcp.call.skipped",
                {"server": provider, "tool": tool, "reason": "unconfigured", "user_id": self.user_id},
            )
            raise RuntimeError(f"MCP provider '{provider}' is not configured.")

        emit_event(
            "mcp.call.started",
            {"server": provider, "tool": tool, "step": self.current_step, "user_id": self.user_id},
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
                    "user_id": self.user_id,
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
                "user_id": self.user_id,
            },
        )
        self._record_response(provider, tool, response)
        self.current_step_action_type = "mcp"
        return response
