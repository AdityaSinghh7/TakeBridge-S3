from __future__ import annotations

import asyncio
import contextvars
import os
from typing import Any, Dict, TYPE_CHECKING

from mcp_agent.actions import SUPPORTED_PROVIDERS
from mcp_agent.user_identity import normalize_user_id, DEV_USER_ENV_VAR, DEV_DEFAULT_USER_ID
from mcp_agent.env_sync import ensure_env_for_provider
from shared.run_context import RUN_LOG_ID

if TYPE_CHECKING:  # pragma: no cover - type checking only
    from mcp_agent.sandbox.runtime import ToolCallResult


def _resolve_user_id() -> str:
    """Resolve user_id from environment variable or default."""
    env_user = os.getenv(DEV_USER_ENV_VAR)
    return normalize_user_id(env_user) if env_user else DEV_DEFAULT_USER_ID


def register_default_tool_caller() -> None:
    """Bind sandbox-generated wrappers to the dispatch_tool architecture."""
    from mcp_agent.sandbox.runtime import register_tool_caller
    from mcp_agent.core.context import AgentContext
    from mcp_agent.actions.dispatcher import dispatch_tool

    # Eagerly set up environment for common providers
    try:
        eager_user = _resolve_user_id()
    except Exception:
        eager_user = None
    else:
        for provider in SUPPORTED_PROVIDERS:
            ensure_env_for_provider(eager_user, provider)

    async def _caller(provider: str, tool: str, payload: Dict[str, Any]) -> "ToolCallResult":
        """
        Bridge sandbox helpers to dispatch_tool architecture.

        Sandbox helpers expect:
          {"successful": bool, "data": <tool-payload>, "error": Any, "logs": Any}
        """
        try:
            # Reconstruct AgentContext from environment
            user_id = _resolve_user_id()
            request_id = os.getenv("TB_REQUEST_ID", "sandbox-default")

            # Ensure provider environment is set up
            ensure_env_for_provider(user_id, provider)

            # Create AgentContext (lazy DB session will be created if needed)
            context = AgentContext(
                user_id=user_id,
                request_id=request_id,
                db_session=None,  # Lazy init
                extra={}
            )

            # Call dispatcher synchronously in executor (dispatcher is sync)
            loop = asyncio.get_running_loop()
            ctx = contextvars.copy_context()

            def _call_sync() -> Dict[str, Any]:
                return dispatch_tool(
                    context=context,
                    provider=provider,
                    tool=tool,
                    payload=payload
                )

            # Propagate run_id (if any) into the executor thread for per-run logging.
            if request_id:
                ctx.run(RUN_LOG_ID.set, request_id)

            response = await loop.run_in_executor(None, lambda: ctx.run(_call_sync))

            # Use single source of truth for unwrapping and success/error handling
            from mcp_agent.execution.response_ops import MCPResponseOps

            ops = MCPResponseOps(response)
            data = ops.unwrap_data()
            result_success = ops.is_success()
            return {
                "success": result_success,
                "successful": result_success,
                "data": data,
                "error": ops.get_error(),
                "logs": None,  # dispatch_tool doesn't return logs field
            }
        except Exception as exc:
            return {
                "success": False,
                "successful": False,
                "error": str(exc),
                "logs": None,
            }

    register_tool_caller(_caller)
