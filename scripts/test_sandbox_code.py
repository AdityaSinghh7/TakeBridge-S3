#!/usr/bin/env python3
"""
Run a sandbox code snippet for a given user id using the existing sandbox engine.

Example:
  python scripts/test_sandbox_code.py --user-id dev-local --code-file ./snippet.py
  python scripts/test_sandbox_code.py --user-id dev-local --code "result = 1+1\nreturn {'x': result}"
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

from mcp_agent.core.context import AgentContext
from mcp_agent.execution.runner import run_python_plan
from mcp_agent.sandbox.ephemeral import generate_ephemeral_toolbox
from mcp_agent.agent.state import AgentState
from mcp_agent.agent.budget import Budget
from mcp_agent.agent.executor import ActionExecutor


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
        "--debug-plan-dir",
        help="If set, sandbox will copy the rendered plan.py to this directory for inspection.",
    )
    parser.add_argument(
        "--via-executor",
        action="store_true",
        help="Run through ActionExecutor._execute_sandbox to see the agent-visible StepResult.",
    )
    return parser.parse_args()


def main() -> int:
    args = _build_args()
    code_body = _read_code(args).rstrip()
    request_id = args.request_id or uuid.uuid4().hex

    # Optional plan debug snapshot
    if args.debug_plan_dir:
        os.environ["TB_SANDBOX_DEBUG_DIR"] = str(Path(args.debug_plan_dir).expanduser().resolve())

    with tempfile.TemporaryDirectory(prefix=f"sandbox-test-{args.user_id}-") as temp_dir:
        toolbox_root = Path(temp_dir)

        # Build agent context and toolbox for this user
        context = AgentContext.create(user_id=args.user_id, request_id=request_id, extra={"toolbox_root": str(toolbox_root)})
        generate_ephemeral_toolbox(context, toolbox_root)

        # Option 1: direct sandbox runner (legacy behavior)
        if not args.via_executor:
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

        # Option 2: run through ActionExecutor to see StepResult as the agent would
        agent_state = AgentState(
            task="sandbox-test",
            user_id=args.user_id,
            request_id=request_id,
            budget=Budget(),
            extra_context={},
        )
        # Allow the sandbox to use googledocs server (minimal search result entry)
        agent_state.merge_search_results(
            [
                {
                    "server": "googledocs",
                    "tool": "googledocs_search_documents",
                    "tool_id": "googledocs.googledocs_search_documents",
                }
            ]
        )

        executor = ActionExecutor(context, agent_state)
        step_result = executor.execute_step(
            {
                "type": "sandbox",
                "code": code_body,
                "label": "test",
                "reasoning": "test run",
            }
        )

        payload: Dict[str, Any] = {
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
            print(f"Success     : {payload['success']}")
            print(f"Error code  : {payload['error_code']}")
            print(f"Error       : {payload['error']}")
            print(f"Preview     : {payload['preview']}")
            print("Observation :")
            print(json.dumps(payload.get("observation"), indent=2, ensure_ascii=False))

        return 0 if step_result.success else 1


if __name__ == "__main__":
    raise SystemExit(main())
