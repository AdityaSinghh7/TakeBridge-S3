#!/usr/bin/env python3
"""
Validate a model output against worker formatters and show code agent step 1 prompts.
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path
from typing import List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from computer_use_agent.utils.common_utils import parse_code_from_string
from computer_use_agent.utils.formatters import (
    CALL_CODE_AGENT_SUBTASK_REQUIRED_FORMATTER,
    CODE_VALID_FORMATTER,
    SINGLE_ACTION_FORMATTER,
)

DEFAULT_OUTPUT = (
    "`\n"
    "agent.call_code_agent(\"Run a Python script to parse the given order JSON and refund policy, "
    "apply the 'damaged' full-refund rule within 30 days, and print the final decision JSON.\")\n"
    "```"
)


class DummyAgent:
    """Minimal agent that satisfies formatter validation."""

    def __init__(self) -> None:
        self.obs = None

    def assign_screenshot(self, obs: dict) -> None:
        self.obs = obs

    def call_code_agent(self, subtask: str) -> str:
        if not isinstance(subtask, str) or not subtask.strip():
            raise ValueError("call_code_agent_task_required")
        if getattr(self, "_validation_only", False):
            return "import time; time.sleep(0.123)"
        raise RuntimeError("call_code_agent should not execute outside validation")


def parse_call_code_agent(code: str) -> Optional[str]:
    try:
        node = ast.parse(code, mode="eval").body
    except Exception:
        return None

    if not isinstance(node, ast.Call):
        return None
    func = node.func
    if not (
        isinstance(func, ast.Attribute)
        and isinstance(func.value, ast.Name)
        and func.value.id == "agent"
        and func.attr == "call_code_agent"
    ):
        return None

    if node.args:
        if len(node.args) != 1 or node.keywords:
            return None
        arg0 = node.args[0]
        if isinstance(arg0, ast.Constant) and isinstance(arg0.value, str):
            return arg0.value
        return None

    if len(node.keywords) != 1:
        return None
    kw = node.keywords[0]
    if kw.arg != "subtask":
        return None
    if isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
        return kw.value.value
    return None


def extract_subtask(output: str) -> Tuple[Optional[str], str]:
    code = parse_code_from_string(output)
    if code:
        subtask = parse_call_code_agent(code)
        if subtask:
            return subtask, "fenced_code_block"

    subtask = parse_call_code_agent(output)
    if subtask:
        return subtask, "raw_output"

    return None, "not_found"


def run_checks(output: str) -> List[Tuple[str, bool, str]]:
    results: List[Tuple[str, bool, str]] = []

    ok, msg = SINGLE_ACTION_FORMATTER(output)
    results.append(("single_action", ok, msg))

    ok, msg = CALL_CODE_AGENT_SUBTASK_REQUIRED_FORMATTER(output)
    results.append(("call_code_agent_subtask_required", ok, msg))

    agent = DummyAgent()
    obs = {"screenshot": ""}
    ok, msg = CODE_VALID_FORMATTER(agent, obs, output)
    results.append(("code_valid", ok, msg))

    return results


def build_code_agent_messages(subtask: str, prompt_path: Path) -> List[dict]:
    system_prompt = prompt_path.read_text(encoding="utf-8").strip()
    user_prompt = (
        f"Task: {subtask}\n\nCurrent screenshot is provided for context."
    )
    return [
        {"role": "developer", "content": [{"type": "text", "text": system_prompt}]},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": user_prompt},
                {
                    "type": "image_url",
                    "image_url": {
                        "url": "data:image/png;base64,<omitted>",
                        "detail": "high",
                    },
                },
            ],
        },
    ]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check a model output against code-agent formatters and print step 1 prompts."
    )
    parser.add_argument(
        "--output",
        default=DEFAULT_OUTPUT,
        help="Model output to validate. Defaults to the provided call_code_agent line.",
    )
    parser.add_argument(
        "--prompt-path",
        default=None,
        help="Optional override for code agent prompt path.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output = args.output.strip()

    repo_root = Path(__file__).resolve().parents[1]
    prompt_path = (
        Path(args.prompt_path)
        if args.prompt_path
        else repo_root / "computer_use_agent" / "coder" / "code_agent_prompt.txt"
    )
    if not prompt_path.exists():
        raise SystemExit(f"Prompt file not found: {prompt_path}")

    print("=== Model Output ===")
    print(output)

    parsed_code = parse_code_from_string(output)
    print("\n=== Parsed Code Block ===")
    print(parsed_code if parsed_code else "(none)")

    print("\n=== Formatter Checks ===")
    results = run_checks(output)
    overall_ok = True
    for name, ok, msg in results:
        status = "PASS" if ok else "FAIL"
        print(f"{name}: {status}")
        if not ok:
            overall_ok = False
            print(f"  reason: {msg}")

    print(f"overall: {'PASS' if overall_ok else 'FAIL'}")

    subtask, source = extract_subtask(output)
    print("\n=== call_code_agent Subtask ===")
    if subtask:
        print(f"source: {source}")
        print(f"subtask: {subtask}")
    else:
        print("not found; skipping code agent prompts")
        return 1

    if not overall_ok:
        print("\nNOTE: output fails formatter checks; prompts shown for reference only.")

    messages = build_code_agent_messages(subtask, prompt_path)
    print("\n=== Code Agent Step 1 Prompts ===")
    print(json.dumps(messages, indent=2, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
