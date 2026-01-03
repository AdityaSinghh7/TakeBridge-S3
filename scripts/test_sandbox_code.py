#!/usr/bin/env python3
"""
Run a sandbox code snippet for a given user id using the existing sandbox engine.

Example:
  python scripts/test_sandbox_code.py --user-id dev-local --code-file ./snippet.py
  python scripts/test_sandbox_code.py --user-id dev-local --code "result = 1+1\nreturn {'x': result}"
  python scripts/test_sandbox_code.py --user-id dev-local --code-file ./snippet.py --mode run-loop
  python scripts/test_sandbox_code.py --user-id dev-local --code-file ./snippet.py --allow-tool shopify.shopify_get_ordersby_id
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from mcp_agent.core.context import AgentContext
from mcp_agent.execution.runner import run_python_plan
from mcp_agent.sandbox.ephemeral import generate_ephemeral_toolbox
from mcp_agent.agent.state import AgentState
from mcp_agent.agent.budget import Budget
from mcp_agent.agent.executor import ActionExecutor
from mcp_agent.agent.run_loop import AgentOrchestrator


def _read_code(args: argparse.Namespace) -> str:
    """Resolve code from --code, --code-file, or stdin."""
    if args.code:
        return args.code
    if args.code_file:
        return Path(args.code_file).read_text(encoding="utf-8")
    if not sys.stdin.isatty():
        return sys.stdin.read()
    raise SystemExit("Provide --code, --code-file, or pipe code via stdin.")


def _print_human(result: Dict[str, Any]) -> None:
    """Pretty-print sandbox result for humans."""
    print(f"Success     : {result['success']}")
    print(f"Timed out   : {result['timed_out']}")
    print(f"Error       : {result.get('error') or ''}")
    print("Result      :")
    print(json.dumps(result.get("result"), indent=2, ensure_ascii=False))
    if result.get("logs"):
        print("\nLogs:")
        for line in result["logs"]:
            print(line)


def _build_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Execute sandbox code for a given user.")
    parser.add_argument("--user-id", required=True, help="User id to scope sandbox.")
    parser.add_argument("--code", help="Inline code body (function body of async main).")
    parser.add_argument("--code-file", help="Path to file containing code body.")
    parser.add_argument("--timeout", type=int, default=30, help="Execution timeout seconds (default: 30).")
    parser.add_argument("--request-id", help="Optional request id (defaults to uuid).")
    parser.add_argument("--python-exec", help="Python executable to run the sandbox (defaults to current).")
    parser.add_argument("--json", dest="json_out", action="store_true", help="Emit JSON only.")
    parser.add_argument(
        "--mode",
        choices=("run-loop", "executor", "runner"),
        default="run-loop",
        help="Execution path: run-loop (AgentOrchestrator) | executor (ActionExecutor) | runner (direct).",
    )
    parser.add_argument(
        "--debug-plan-dir",
        help="If set, sandbox will copy the rendered plan.py to this directory for inspection.",
    )
    parser.add_argument(
        "--via-executor",
        action="store_true",
        help="Deprecated: use --mode executor. Run through ActionExecutor._execute_sandbox.",
    )
    parser.add_argument(
        "--via-run-loop",
        action="store_true",
        help="Deprecated: use --mode run-loop. Run through AgentOrchestrator.",
    )
    parser.add_argument(
        "--allow-tool",
        action="append",
        default=[],
        help="Whitelist a tool for sandbox guardrails (provider.tool). Repeatable or comma-separated.",
    )
    return parser.parse_args()


def _parse_allow_tools(raw_values: List[str]) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    for raw in raw_values or []:
        for entry in (raw or "").split(","):
            entry = entry.strip()
            if not entry:
                continue
            if "." not in entry:
                raise SystemExit(f"--allow-tool must be provider.tool (got '{entry}')")
            provider, tool = entry.split(".", 1)
            provider = provider.strip()
            tool = tool.strip()
            if not provider or not tool:
                raise SystemExit(f"--allow-tool must be provider.tool (got '{entry}')")
            results.append(
                {
                    "server": provider,
                    "provider": provider,
                    "tool": tool,
                    "tool_id": f"{provider}.{tool}",
                }
            )
    return results


def _resolve_mode(args: argparse.Namespace) -> str:
    if args.via_executor:
        return "executor"
    if args.via_run_loop:
        return "run-loop"
    return args.mode


def _seed_search_results(agent_state: AgentState, allow_tools: List[Dict[str, Any]]) -> None:
    if not allow_tools:
        return
    agent_state.merge_search_results(allow_tools)


class _SandboxPlanner:
    def __init__(self, code_body: str, *, label: str = "test") -> None:
        self._code_body = code_body
        self._label = label
        self.model = "sandbox-test"

    def is_enabled(self) -> bool:
        return True

    def generate_plan(self, context: AgentState) -> Dict[str, Any]:
        last_step = context.history[-1] if context.history else None
        if last_step and last_step.action_type == "sandbox":
            if last_step.success:
                command = {
                    "type": "finish",
                    "reasoning": "sandbox test complete",
                    "summary": "sandbox test complete",
                }
            else:
                command = {
                    "type": "fail",
                    "reasoning": "sandbox test failed",
                    "reason": last_step.error or "sandbox failed",
                }
            return {"text": json.dumps(command)}

        command = {
            "type": "sandbox",
            "reasoning": "sandbox test run",
            "code": self._code_body,
            "label": self._label,
        }
        return {"text": json.dumps(command)}


def _extract_sandbox_step(result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    steps = result.get("steps") or []
    for step in reversed(steps):
        if step.get("action_type") == "sandbox":
            return step
    return None


def main() -> int:
    args = _build_args()
    code_body = _read_code(args).rstrip()
    request_id = args.request_id or uuid.uuid4().hex
    mode = _resolve_mode(args)
    allow_tools = _parse_allow_tools(args.allow_tool)

    # Optional plan debug snapshot
    if args.debug_plan_dir:
        os.environ["TB_SANDBOX_DEBUG_DIR"] = str(Path(args.debug_plan_dir).expanduser().resolve())

    with tempfile.TemporaryDirectory(prefix=f"sandbox-test-{args.user_id}-") as temp_dir:
        toolbox_root = Path(temp_dir)

        # Build agent context and toolbox for this user
        context = AgentContext.create(user_id=args.user_id, request_id=request_id, extra={"toolbox_root": str(toolbox_root)})
        generate_ephemeral_toolbox(context, toolbox_root)

        # Option 1: direct sandbox runner (legacy behavior)
        if mode == "runner":
            result = run_python_plan(
                context,
                code_body,
                timeout_sec=args.timeout,
                python_executable=args.python_exec or sys.executable,
                label="test",
            )

            payload: Dict[str, Any] = {
                "success": result.success,
                "timed_out": result.timed_out,
                "error": result.error,
                "result": result.result,
                "logs": result.logs,
            }

            if args.json_out:
                print(json.dumps(payload, indent=2, ensure_ascii=False))
            else:
                _print_human(payload)

            return 0 if (result.success and not result.timed_out) else 1

        if mode == "executor":
            # Option 2: run through ActionExecutor to see StepResult as the agent would
            agent_state = AgentState(
                task="sandbox-test",
                user_id=args.user_id,
                request_id=request_id,
                budget=Budget(),
                extra_context={},
            )
            _seed_search_results(agent_state, allow_tools)

            executor = ActionExecutor(context, agent_state)
            step_result = executor.execute_step(
                {
                    "type": "sandbox",
                    "code": code_body,
                    "label": "test",
                    "reasoning": "test run",
                }
            )

            payload = {
                "success": step_result.success,
                "error_code": step_result.error_code,
                "error": step_result.error,
                "timed_out": bool(getattr(step_result, "timed_out", False)),
                "preview": step_result.preview,
                "observation": step_result.observation,
                "is_smart_summary": step_result.is_smart_summary,
                "raw_output_key": step_result.raw_output_key,
            }

            if args.json_out:
                print(json.dumps(payload, indent=2, ensure_ascii=False))
            else:
                print(f"Mode        : executor")
                print(f"Success     : {payload['success']}")
                print(f"Error code  : {payload['error_code']}")
                print(f"Error       : {payload['error']}")
                print(f"Preview     : {payload['preview']}")
                print("Observation :")
                print(json.dumps(payload.get("observation"), indent=2, ensure_ascii=False))

            return 0 if step_result.success else 1

        # Option 3: run through AgentOrchestrator (run_loop -> executor -> runner)
        if args.timeout != 30 or args.python_exec:
            print("Note: --timeout/--python-exec are ignored in run-loop mode.")
        agent_state = AgentState(
            task="sandbox-test",
            user_id=args.user_id,
            request_id=request_id,
            budget=Budget(),
            extra_context={},
        )
        _seed_search_results(agent_state, allow_tools)

        llm = _SandboxPlanner(code_body, label="test")
        runtime = AgentOrchestrator(context, agent_state, llm=llm)
        result = runtime.run()

        sandbox_step = _extract_sandbox_step(result or {})
        payload = {
            "mode": "run-loop",
            "success": result.get("success"),
            "error_code": result.get("error_code"),
            "error": result.get("error_message") or result.get("error"),
            "final_summary": result.get("final_summary"),
            "run_id": result.get("run_id"),
            "steps": len(result.get("steps") or []),
            "sandbox_step": sandbox_step,
        }

        if args.json_out:
            print(json.dumps(payload, indent=2, ensure_ascii=False))
        else:
            print(f"Mode        : run-loop")
            print(f"Success     : {payload['success']}")
            print(f"Error code  : {payload['error_code']}")
            print(f"Error       : {payload['error']}")
            print(f"Summary     : {payload['final_summary']}")
            print(f"Run ID      : {payload['run_id']}")
            print(f"Steps       : {payload['steps']}")
            if sandbox_step:
                print("Sandbox step:")
                print(json.dumps(sandbox_step, indent=2, ensure_ascii=False))

        return 0 if result.get("success") else 1


if __name__ == "__main__":
    raise SystemExit(main())
