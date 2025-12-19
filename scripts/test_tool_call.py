#!/usr/bin/env python3
"""
Execute a single MCP tool call through the planner path:
 - optional search to populate available_tools
 - execute_step() -> StepResult
 - AgentOrchestrator._handle_action_result() to mirror planner handling

Examples:
  python scripts/test_tool_call.py \
    --user-id dev-local \
    --tool-id googledocs.googledocs_search_documents \
    --server googledocs \
    --args '{"query": "policy", "max_results": 5}' \
    --search-query "googledocs search"

  python scripts/test_tool_call.py \
    --user-id dev-local \
    --provider googledocs \
    --tool googledocs_get_document_by_id \
    --args '{"doc_id": "123"}'
"""

from __future__ import annotations

import argparse
import json
import tempfile
import uuid
from pathlib import Path

from mcp_agent.agent.budget import Budget
from mcp_agent.agent.executor import ActionExecutor
from mcp_agent.agent.llm import PlannerLLM
from mcp_agent.agent.run_loop import AgentOrchestrator
from mcp_agent.agent.state import AgentState
from mcp_agent.core.context import AgentContext
from mcp_agent.sandbox.ephemeral import generate_ephemeral_toolbox


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Execute a single MCP tool call through the planner path.")
    parser.add_argument("--user-id", required=True, help="User id to scope toolbox.")
    # Tool selection (either tool_id+server or provider+tool)
    parser.add_argument("--tool-id", help="Fully qualified tool id (e.g., googledocs.googledocs_search_documents).")
    parser.add_argument("--server", help="Server name when using --tool-id (e.g., googledocs).")
    parser.add_argument("--provider", help="Provider name (e.g., googledocs).")
    parser.add_argument("--tool", help="Tool name (e.g., googledocs_search_documents).")
    parser.add_argument("--args", default="{}", help="JSON object of arguments/payload for the tool.")
    parser.add_argument("--search-query", help="Optional search query to run first (populates available_tools).")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        payload = json.loads(args.args)
        if not isinstance(payload, dict):
            raise ValueError("args must be a JSON object")
    except Exception as exc:  # pragma: no cover - CLI validation
        raise SystemExit(f"Invalid --args JSON: {exc}")

    request_id = uuid.uuid4().hex

    with tempfile.TemporaryDirectory(prefix=f"tool-test-{args.user_id}-") as temp_dir:
        toolbox_root = Path(temp_dir)

        # Build agent context and toolbox for this user
        context = AgentContext.create(
            user_id=args.user_id,
            request_id=request_id,
            extra={"toolbox_root": str(toolbox_root)},
        )
        generate_ephemeral_toolbox(context, toolbox_root)

        # Agent state and orchestrator/executor (LLM disabled; we only use planner utilities)
        state = AgentState(
            task="tool-test",
            user_id=args.user_id,
            request_id=request_id,
            budget=Budget(),
            extra_context={},
        )
        orchestrator = AgentOrchestrator(context, state, llm=PlannerLLM(enabled=False))
        executor = ActionExecutor(context, state)

        # Optional search to populate available_tools (mirrors planner search step)
        if args.search_query:
            search_cmd = {
                "type": "search",
                "query": args.search_query,
                "reasoning": "preload tool schema via search",
            }
            search_result = executor.execute_step(search_cmd)
            orchestrator._handle_action_result(search_cmd, search_result)

        # Build tool command
        if args.tool_id and args.server:
            cmd = {
                "type": "tool",
                "tool_id": args.tool_id,
                "server": args.server,
                "args": payload,
                "reasoning": "direct tool test",
            }
        elif args.provider and args.tool:
            cmd = {
                "type": "tool",
                "provider": args.provider,
                "tool": args.tool,
                "payload": payload,
                "reasoning": "direct tool test",
            }
        else:
            raise SystemExit("Provide either --tool-id AND --server, or --provider AND --tool.")

        # Execute tool and process result through orchestrator handler
        step_result = executor.execute_step(cmd)
        action_result = orchestrator._handle_action_result(cmd, step_result)

        # Print outcomes
        print("=== StepResult (execute_step) ===")
        print(f"success      : {step_result.success}")
        print(f"error_code   : {step_result.error_code}")
        print(f"error        : {step_result.error}")
        print(f"preview      : {step_result.preview}")
        print(f"observation  : {step_result.observation}")

        print("\n=== _handle_action_result output ===")
        if action_result is None:
            print("Result       : None (loop would continue)")
        else:
            print(json.dumps(action_result, indent=2, ensure_ascii=False))

        return 0 if step_result.success else 1


if __name__ == "__main__":
    raise SystemExit(main())
