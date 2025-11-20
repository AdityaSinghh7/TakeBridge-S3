from __future__ import annotations

from typing import Callable, Dict, Tuple

from mcp_agent.actions import get_provider_action_map

from .docstring_specs import build_iotoolspec_from_func
from .schema_store import load_output_schemas
from .registry import register_tool


_IO_SPECS_LOADED: bool = False


def ensure_io_specs_loaded() -> None:
    """
    Lazily register IoToolSpecs for known MCP actions and merge any generated
    output schemas into them.

    This is invoked on-demand by search_tools(...) so that planner discovery
    always sees up-to-date IO metadata without introducing import cycles.
    """
    global _IO_SPECS_LOADED
    if _IO_SPECS_LOADED:
        return

    action_map: Dict[str, Tuple[Callable[..., object], ...]] = get_provider_action_map()
    for provider, funcs in action_map.items():
        for func in funcs:
            spec = build_iotoolspec_from_func(provider=provider, func=func)
            register_tool(spec)

    # Optionally enrich IoToolSpecs with generated output schemas.
    load_output_schemas()

    _IO_SPECS_LOADED = True

