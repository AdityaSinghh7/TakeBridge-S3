from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


@dataclass(frozen=True)
class ToolDescription:
    """Metadata about an MCP action that can be surfaced in system prompts."""

    provider: str
    name: str
    doc: str


@dataclass(frozen=True)
class ToolCallContext:
    """Container describing the provider/tool/payload for an MCP invocation."""

    provider: str
    tool: str
    payload: Dict[str, Any]


@runtime_checkable
class MCPToolBridge(Protocol):
    """Abstract bridge used by the worker to communicate with MCP tooling."""

    def set_step(self, step_index: Optional[int]) -> None:
        """Tell the bridge which runner step is active."""

    def finalize_step(self) -> None:
        """Mark the current step as completed."""

    def call_tool(self, context: ToolCallContext) -> Dict[str, Any]:
        """Invoke a provider/tool pair with the supplied payload."""

    @property
    def last_response(self) -> Optional[Dict[str, Any]]:
        """Return the most recent MCP response if available."""

    @property
    def last_action_type(self) -> Optional[str]:
        """Whether the last action executed was MCP or GUI."""

    @property
    def current_step_action_type(self) -> Optional[str]:
        """Action type for the step currently in-flight."""

    @property
    def history(self) -> Dict[str, List[Dict[str, Any]]]:
        """Historic tool responses grouped by tool name."""

    def available_actions(self) -> List[ToolDescription]:
        """Return metadata about all MCP actions currently available."""


class NullMCPToolBridge(MCPToolBridge):
    """No-op implementation used when MCP is disabled."""

    def __init__(self) -> None:
        self._history: Dict[str, List[Dict[str, Any]]] = {}
        self._last_response: Optional[Dict[str, Any]] = None
        self._last_action_type: Optional[str] = None
        self._current_step_action_type: Optional[str] = None

    def set_step(self, step_index: Optional[int]) -> None:  # noqa: D401 - protocol impl
        self._current_step_action_type = None

    def finalize_step(self) -> None:  # noqa: D401 - protocol impl
        self._last_action_type = self._current_step_action_type
        self._current_step_action_type = None

    def call_tool(self, context: ToolCallContext) -> Dict[str, Any]:  # noqa: D401
        raise RuntimeError("MCP tooling is not configured for this run.")

    @property
    def last_response(self) -> Optional[Dict[str, Any]]:
        return self._last_response

    @property
    def last_action_type(self) -> Optional[str]:
        return self._last_action_type

    @property
    def current_step_action_type(self) -> Optional[str]:
        return self._current_step_action_type

    @property
    def history(self) -> Dict[str, List[Dict[str, Any]]]:
        return self._history

    def available_actions(self) -> List[ToolDescription]:  # noqa: D401 - protocol impl
        return []
