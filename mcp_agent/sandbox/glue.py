from __future__ import annotations

import os
from typing import Any, Dict, TYPE_CHECKING

from mcp_agent.user_identity import require_env_user_id
from mcp_agent.env_sync import ensure_env_for_provider

if TYPE_CHECKING:  # pragma: no cover - type checking only
    from sandbox_py.client import ToolCallResult


def _resolve_user_id() -> str:
    return require_env_user_id()


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

    use_stubs = os.getenv("MCP_USE_HTTP_STUBS", "") == "1" or os.getenv("PYTEST_CURRENT_TEST")
    if ensure_test_stubs and use_stubs:
        ensure_test_stubs()

    from mcp_agent.mcp_agent import MCPAgent

    try:
        eager_user = _resolve_user_id()
    except Exception:
        eager_user = None
    else:
        for provider in ("gmail", "slack"):
            ensure_env_for_provider(eager_user, provider)

    async def _caller(provider: str, tool: str, payload: Dict[str, Any]) -> "ToolCallResult":
        try:
            user_id = _resolve_user_id()
            for prov in (provider,):
                ensure_env_for_provider(user_id, prov)
            agent = MCPAgent.current(user_id)
            if hasattr(agent, "acall_tool"):
                response = await agent.acall_tool(provider, tool, payload)  # type: ignore[attr-defined]
            else:  # pragma: no cover - legacy/test stubs
                import asyncio

                loop = asyncio.get_running_loop()

                def _call_sync() -> Dict[str, Any]:
                    return agent.call_tool(provider, tool, payload)

                response = await loop.run_in_executor(None, _call_sync)
            return {"successful": True, "data": response}
        except Exception as exc:  # pragma: no cover - exception propagation
            return {"successful": False, "error": str(exc)}

    register_tool_caller(_caller)
