from __future__ import annotations

import os
from typing import Any, Dict, TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - type checking only
    from sandbox_py.client import ToolCallResult


def _resolve_user_id() -> str:
    return (os.getenv("TB_USER_ID") or "singleton").strip() or "singleton"


def register_default_tool_caller() -> None:
    """
    Bind sandbox-generated wrappers to the active MCPAgent.

    No-op when `TB_DISABLE_SANDBOX_CALLER=1` so tests can opt out or inject their own callers.
    """

    if os.getenv("TB_DISABLE_SANDBOX_CALLER") == "1":
        return

    try:
        from sandbox_py.client import register_tool_caller
    except ModuleNotFoundError as exc:  # pragma: no cover - misconfigured toolbox
        raise RuntimeError("sandbox_py package is missing. Run ToolboxBuilder.persist() first.") from exc

    try:
        from mcp_agent.testing.stubs import ensure_test_stubs
    except Exception:  # pragma: no cover - optional helper
        ensure_test_stubs = None  # type: ignore[assignment]

    if ensure_test_stubs:
        ensure_test_stubs()

    from mcp_agent.mcp_agent import MCPAgent

    async def _caller(provider: str, tool: str, payload: Dict[str, Any]) -> "ToolCallResult":
        try:
            user_id = _resolve_user_id()
            response = MCPAgent.current(user_id).call_tool(provider, tool, payload)
            return {"successful": True, "data": response}
        except Exception as exc:  # pragma: no cover - exception propagation
            return {"successful": False, "error": str(exc)}

    register_tool_caller(_caller)
