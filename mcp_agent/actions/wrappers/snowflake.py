from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict

from mcp_agent.types import ToolInvocationResult

from ._common import _clean_payload, _invoke_mcp_tool, ensure_authorized

if TYPE_CHECKING:
    from mcp_agent.core.context import AgentContext


def snowflake_execute_sql(
    context: "AgentContext",
    statement: str,
    bindings: Dict[str, Any] | None = None,
    database: str | None = None,
    parameters: Dict[str, Any] | None = None,
    role: str | None = None,
    schema_name: str | None = None,
    timeout: int | None = None,
    warehouse: str | None = None,
) -> ToolInvocationResult:
    """
    Execute a SQL statement against Snowflake and return the resulting data.
    """
    provider = "snowflake"
    tool_name = "SNOWFLAKE_EXECUTE_SQL"
    ensure_authorized(context, provider)
    payload = _clean_payload(
        {
            "statement": statement,
            "bindings": bindings,
            "database": database,
            "parameters": parameters,
            "role": role,
            "schema_name": schema_name,
            "timeout": timeout,
            "warehouse": warehouse,
        }
    )
    return _invoke_mcp_tool(context, provider, tool_name, payload)
