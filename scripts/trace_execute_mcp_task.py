 #!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from contextlib import contextmanager
from typing import Any, Dict, List, Optional

from mcp_agent.mcp_agent import MCPAgent
from mcp_agent.registry.oauth import OAuthManager
from mcp_agent.agent import execute_mcp_task
from mcp_agent.core.context import AgentContext
from mcp_agent.dev import resolve_dev_user


def _json_dump(value: Any) -> str:
    try:
        return json.dumps(value, indent=2, ensure_ascii=False, default=str)
    except TypeError:
        return json.dumps(str(value), indent=2, ensure_ascii=False)


def _deep_copy(value: Any) -> Any:
    try:
        return json.loads(json.dumps(value, ensure_ascii=False, default=str))
    except TypeError:
        return value


def ensure_provider_ready(provider: str, user_id: str) -> None:
    print(f"[setup] Checking OAuth state for provider={provider!r}, user_id={user_id!r}...")
    context = AgentContext.create(user_id)
    if not OAuthManager.is_authorized(context, provider):
        raise RuntimeError(
            f"Provider '{provider}' is not authorized for user '{user_id}'. "
            "Complete the OAuth flow before running this script."
        )
    # Registry is DB-backed, no manual refresh needed


@contextmanager
def capture_mcp_calls() -> List[Dict[str, Any]]:
    original_call = MCPAgent.call_tool
    captured: List[Dict[str, Any]] = []

    def _wrapped(self: MCPAgent, provider: str, tool: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        record: Dict[str, Any] = {
            "step": self.current_step,
            "provider": provider,
            "tool": tool,
            "payload": _deep_copy(payload),
        }
        captured.append(record)
        response = original_call(self, provider, tool, payload)
        record["response"] = _deep_copy(response)
        return response

    MCPAgent.call_tool = _wrapped  # type: ignore[assignment]
    try:
        yield captured
    finally:
        MCPAgent.call_tool = original_call


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run execute_mcp_task(...) and trace MCP tool payloads/responses."
    )
    parser.add_argument("task", help="Natural language task for the planner to execute.")
    parser.add_argument(
        "--user-id",
        default=None,
        help="Tenant/user id to scope the run. Defaults to TB_USER_ID or dev-local.",
    )
    parser.add_argument(
        "--provider",
        default="gmail",
        help="Provider to ensure OAuth is refreshed for (default: gmail).",
    )
    parser.add_argument(
        "--extra-context",
        default=None,
        help="Optional JSON string with extra context passed to execute_mcp_task.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    user_id = args.user_id or resolve_dev_user()
    try:
        ensure_provider_ready(args.provider, user_id)
    except Exception as exc:  # pragma: no cover - CLI convenience
        print(f"[error] Failed to sync OAuth for provider '{args.provider}': {exc}", file=sys.stderr)
        sys.exit(1)

    if args.extra_context:
        try:
            extra_context: Optional[Dict[str, Any]] = json.loads(args.extra_context)
        except json.JSONDecodeError as exc:  # pragma: no cover - CLI convenience
            print(f"[error] extra_context must be valid JSON: {exc}", file=sys.stderr)
            sys.exit(1)
    else:
        extra_context = None

    print("[run] Executing planner task...")
    with capture_mcp_calls() as calls:
        result = execute_mcp_task(
            args.task,
            user_id=user_id,
            extra_context=extra_context,
        )

    print("\n=== Planner Result ===")
    print(f"Success: {result.get('success')}")
    print(f"Final summary: {result.get('final_summary')}")
    if result.get("error"):
        print(f"Error: {result['error']}")

    print("\n=== Tool Call Trace ===")
    if not calls:
        print("No MCP tool calls were made.")
    for idx, call in enumerate(calls, start=1):
        print(f"\nCall #{idx} (step={call.get('step')}): {call['provider']}.{call['tool']}")
        print("Payload:")
        print(_json_dump(call["payload"]))
        print("Response:")
        print(_json_dump(call.get("response")))

    print("\n=== Planner Logs ===")
    for log in result.get("logs", []):
        print(_json_dump(log))

    print("\n=== Raw Outputs ===")
    print(_json_dump(result.get("raw_outputs", {})))


if __name__ == "__main__":
    main()
