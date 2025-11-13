from __future__ import annotations

from typing import List, Tuple

from computer_use_agent.grounding.grounding_agent import ACI
from mcp_agent.actions import iter_available_action_functions
from shared.streaming import emit_event

_REGISTERED_ACTION_NAMES: set[str] = set()


def _remove_registered_actions() -> None:
    """Remove all previously attached MCP action shims from the ACI class."""
    for action_name in list(_REGISTERED_ACTION_NAMES):
        if hasattr(ACI, action_name):
            try:
                delattr(ACI, action_name)
            except Exception:
                pass
    _REGISTERED_ACTION_NAMES.clear()


def sync_registered_actions() -> None:
    """Synchronize MCP action shims on the ACI with currently available tools."""
    _remove_registered_actions()
    registered: List[Tuple[str, str]] = []
    for provider, fn in iter_available_action_functions():
        setattr(ACI, fn.__name__, fn)
        registered.append((provider, fn.__name__))
        _REGISTERED_ACTION_NAMES.add(fn.__name__)
    if registered:
        emit_event(
            "mcp.actions.registration.completed",
            {
                "actions": [
                    {"provider": provider, "action": action} for provider, action in registered
                ]
            },
        )
    else:
        emit_event(
            "mcp.actions.registration.skipped",
            {"reason": "no_available_actions"},
        )
