#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict

from mcp_agent.dev import resolve_dev_user, run_dev_task
from mcp_agent.planner.llm import PlannerLLM
from mcp_agent.env_sync import ensure_env_for_provider

DEFAULT_RECIPIENT = "adityadevsinghs@gmail.com"
DEFAULT_TASK_TEMPLATE = (
    "Retrieve the three most recent emails in my Gmail inbox, produce a concise explanation "
    "for each (including any follow-up required), then send one email to {recipient} summarizing "
    "those findings and any recommended next actions."
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the MCP planner against the dev-local Gmail workflow.",
    )
    parser.add_argument(
        "--task",
        help="Override the natural-language task issued to the planner.",
    )
    parser.add_argument(
        "--recipient",
        default=DEFAULT_RECIPIENT,
        help=f"Recipient email used by the default task template (default: {DEFAULT_RECIPIENT}).",
    )
    parser.add_argument(
        "--user-id",
        default=None,
        help="User id to scope registry/OAuth state (defaults to TB_USER_ID or dev-local).",
    )
    parser.add_argument(
        "--model",
        default="o4-mini",
        help="LLM model name to use for the planner (default: o4-mini).",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print the resulting JSON instead of a minimal summary.",
    )
    return parser


def run(task: str, user_id: str, model: str) -> Dict[str, Any]:
    llm = PlannerLLM(model=model, enabled=True)
    result = run_dev_task(task, user_id=user_id, llm=llm)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    user_id = resolve_dev_user(args.user_id)
    task = args.task or DEFAULT_TASK_TEMPLATE.format(recipient=args.recipient)

    # Ensure downstream components know the active user + enable summaries
    os.environ.setdefault("TB_USER_ID", user_id)
    os.environ["MCP_PLANNER_LLM_ENABLED"] = "1"
    for provider in ("gmail", "slack"):
        ensure_env_for_provider(user_id, provider)

    try:
        result = run(task, user_id=user_id, model=args.model)
    except Exception as exc:  # pragma: no cover - runtime guardrail
        print(f"[error] Planner execution failed: {exc}", file=sys.stderr)
        return 1

    if args.pretty:
        print(json.dumps(result, indent=2, default=str))
    else:
        summary = result.get("final_summary") or "(no summary)"
        print(f"Success: {result.get('success')} | Summary: {summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
