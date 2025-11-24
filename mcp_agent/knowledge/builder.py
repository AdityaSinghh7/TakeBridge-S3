"""
Compatibility shim for the previous knowledge.builder module.

Routes and callers still import `get_manifest`/`refresh_manifest` from
`mcp_agent.knowledge.builder`. The implementations now live in
`mcp_agent.knowledge.introspection`, so we forward to that module.
"""

from __future__ import annotations

from mcp_agent.knowledge.introspection import get_manifest  # re-export


def refresh_manifest(*args, **kwargs):
    """
    Backwards-compatible alias. The underlying manifest is generated on demand
    in `get_manifest`, so refresh simply delegates.
    """
    return get_manifest(*args, **kwargs)
