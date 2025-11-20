from __future__ import annotations

from typing import Dict, List

from .io_spec import ToolSpec

_TOOL_REGISTRY: Dict[str, ToolSpec] = {}


def _key(provider: str, tool_name: str) -> str:
    return f"{provider}.{tool_name}"


def register_tool(spec: ToolSpec) -> None:
    """
    Register a tool specification for use by probing and documentation helpers.

    This registry is intentionally decoupled from the runtime toolbox index
    used by the planner; it is safe to use in dev scripts without impacting
    planner behavior.
    """
    _TOOL_REGISTRY[_key(spec.provider, spec.tool_name)] = spec


def get_tool_spec(provider: str, tool_name: str) -> ToolSpec | None:
    return _TOOL_REGISTRY.get(_key(provider, tool_name))


def all_tools() -> List[ToolSpec]:
    return list(_TOOL_REGISTRY.values())

