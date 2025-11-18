from __future__ import annotations

from typing import Any, Callable, Dict, Optional


def tool_output_schema(
    schema: Dict[str, Any],
    pretty: Optional[str] = None,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """
    Attach a description of an MCP tool's `data` field schema to a wrapper function.

    The `schema` argument should describe the structure under the canonical
    `{ success: bool, data: dict, error: str | null }` envelope.

    For now, callers may pass placeholder text for `pretty` when the exact
    Composio-compatible payload format is not yet known. In those cases,
    ensure the text clearly notes that it must be replaced with the real
    response schema in a follow-up pass.
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        setattr(func, "__tb_output_schema__", schema)
        if pretty is not None:
            setattr(func, "__tb_output_schema_pretty__", pretty)
        return func

    return decorator

