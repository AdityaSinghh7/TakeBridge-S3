from __future__ import annotations

import asyncio
import os
from importlib import import_module
from typing import Any, Dict, TYPE_CHECKING

from mcp_agent.user_identity import normalize_user_id, DEV_USER_ENV_VAR, DEV_DEFAULT_USER_ID
from mcp_agent.env_sync import ensure_env_for_provider

if TYPE_CHECKING:  # pragma: no cover - type checking only
    from sandbox_py.client import ToolCallResult


def _resolve_user_id() -> str:
    """Resolve user_id from environment variable or default."""
    env_user = os.getenv(DEV_USER_ENV_VAR)
    return normalize_user_id(env_user) if env_user else DEV_DEFAULT_USER_ID


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

    fake_factory_path = os.getenv("MCP_FAKE_CLIENT_FACTORY", "").strip()

    use_stubs = (
        os.getenv("MCP_USE_HTTP_STUBS", "") == "1"
        or os.getenv("PYTEST_CURRENT_TEST")
        or bool(fake_factory_path)
    )
    if ensure_test_stubs and use_stubs:
        ensure_test_stubs()

    # When a fake factory is configured (tests), avoid importing the full MCP
    # client stack and instead bridge directly to the stub clients.
    if fake_factory_path:
        module_name, func_name = fake_factory_path.rsplit(":", 1)
        module = import_module(module_name)
        factory = getattr(module, func_name)

        clients: Dict[str, Any] | None = None

        async def _caller(provider: str, tool: str, payload: Dict[str, Any]) -> "ToolCallResult":
            """
            Bridge sandbox helpers to fake MCP clients provided by tests.

            This path is used when MCP_FAKE_CLIENT_FACTORY is set and does not
            depend on the external `mcp` Python package.
            """
            nonlocal clients
            try:
                user_id = _resolve_user_id()
            except Exception:
                user_id = None

            if clients is None:
                # Factories may or may not accept a user_id kwarg.
                try:
                    if user_id is not None:
                        created = factory(user_id=user_id)
                    else:
                        created = factory()
                except TypeError:
                    created = factory()
                if not isinstance(created, dict):
                    raise RuntimeError(
                        "Fake client factory must return a dict of provider -> client instances."
                    )
                clients = created

            client = clients.get(provider)
            if client is None:
                raise RuntimeError(f"Stub MCP provider '{provider}' missing.")

            if hasattr(client, "acall"):
                response = await client.acall(tool, payload)
            else:  # pragma: no cover - sync fake clients
                loop = asyncio.get_running_loop()

                def _call_sync() -> Dict[str, Any]:
                    return client.call(tool, payload)

                response = await loop.run_in_executor(None, _call_sync)

            from mcp_agent.execution.envelope import normalize_action_response, unwrap_nested_data

            envelope = normalize_action_response(response)
            data = unwrap_nested_data(envelope["data"])
            result_success = bool(envelope["successful"])
            return {
                "success": result_success,
                "successful": result_success,
                "data": data,
                "error": envelope.get("error"),
                "logs": (response or {}).get("logs") if isinstance(response, dict) else None,
            }

        register_tool_caller(_caller)
        return

    from mcp_agent.mcp_agent import MCPAgent

    try:
        eager_user = _resolve_user_id()
    except Exception:
        eager_user = None
    else:
        for provider in ("gmail", "slack"):
            ensure_env_for_provider(eager_user, provider)

    async def _caller(provider: str, tool: str, payload: Dict[str, Any]) -> "ToolCallResult":
        """
        Bridge sandbox helpers to MCPAgent while normalizing the result shape.

        Sandbox helpers expect a single envelope:
          {"successful": bool, "data": <tool-payload>, "error": Any, "logs": Any}
        """
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

            # Normalize into a canonical envelope, then adapt to sandbox expectations.
            from mcp_agent.execution.envelope import normalize_action_response, unwrap_nested_data

            envelope = normalize_action_response(response)
            data = unwrap_nested_data(envelope["data"])
            result_success = bool(envelope["successful"])
            return {
                "success": result_success,
                "successful": result_success,
                "data": data,
                "error": envelope.get("error"),
                "logs": (response or {}).get("logs") if isinstance(response, dict) else None,
            }
        except Exception as exc:  # pragma: no cover - exception propagation
            return {
                "success": False,
                "successful": False,
                "error": str(exc),
                "logs": None,
            }

    register_tool_caller(_caller)
