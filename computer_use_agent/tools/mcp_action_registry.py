from __future__ import annotations

from typing import List, Tuple

from computer_use_agent.grounding.grounding_agent import ACI
from mcp_agent.actions import iter_available_action_functions
from mcp_agent.toolbox import refresh_manifest
from mcp_agent.user_identity import normalize_user_id
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


def sync_registered_actions(user_id: str) -> None:
    """Synchronize MCP action shims on the ACI with currently available tools."""
    active_user = normalize_user_id(user_id)
    _remove_registered_actions()
    registered: List[Tuple[str, str]] = []
    for provider, fn in iter_available_action_functions(user_id=active_user):
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
    try:
        refresh_manifest(user_id=active_user)
    except Exception as exc:
        emit_event(
            "mcp.toolbox.refresh.failed",
            {"error": str(exc)},
        )
