#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict

import requests

try:
    from dotenv import load_dotenv  # type: ignore
except Exception:  # pragma: no cover
    load_dotenv = None


def load_payload(path: Path) -> Dict[str, Any]:
    try:
        data = path.read_text(encoding="utf-8")
        return json.loads(data)
    except Exception as exc:
        raise ValueError(f"Failed to load payload from {path}: {exc}") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Trigger /orchestrate on the TakeBridge server.")
    parser.add_argument("--task", required=True, help="Task instruction for the orchestrator.")
    parser.add_argument("--host", default="127.0.0.1", help="Server host (default: 127.0.0.1).")
    parser.add_argument("--port", default="8000", help="Server port (default: 8000).")
    parser.add_argument("--payload", type=Path, help="Path to JSON file with additional payload overrides.")
    parser.add_argument(
        "--json",
        help="Inline JSON string with overrides (merged after --payload).",
    )
    parser.add_argument(
        "--enable-code-execution",
        action="store_true",
        help="Enable code execution in the orchestrator environment.",
    )
    parser.add_argument(
        "--save",
        type=Path,
        help="Optional path to save the full JSON response.",
    )

    args = parser.parse_args(argv)

    if load_dotenv:
        load_dotenv()

    payload: Dict[str, Any] = {"task": args.task}

    if args.payload:
        payload.update(load_payload(args.payload))

    if args.json:
        try:
            payload.update(json.loads(args.json))
        except Exception as exc:
            raise ValueError(f"Invalid JSON passed via --json: {exc}") from exc

    if args.enable_code_execution:
        payload.setdefault("enable_code_execution", True)

    url = f"http://{args.host}:{args.port}/orchestrate"
    print(f"POST {url}")
    print(json.dumps(payload, indent=2, ensure_ascii=False))

    try:
        start = time.perf_counter()
        response = requests.post(url, json=payload, timeout=None)
        duration = time.perf_counter() - start
    except requests.RequestException as exc:
        print(f"Request failed: {exc}", file=sys.stderr)
        return 1

    print(f"\nStatus code: {response.status_code} (completed in {duration:.2f}s)")

    if response.status_code != 200:
        print(response.text)
        return 1

    try:
        data = response.json()
    except ValueError:
        print("Failed to parse JSON response:", response.text, file=sys.stderr)
        return 1

    if args.save:
        try:
            args.save.parent.mkdir(parents=True, exist_ok=True)
            args.save.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
            print(f"Full response saved to {args.save}")
        except Exception as exc:
            print(f"Failed to save response: {exc}", file=sys.stderr)

    # Pretty-print summary
    print("\n=== Orchestration Summary ===")
    print(f"Task: {data.get('task')}")
    print(f"Status: {data.get('status')}  Completion: {data.get('completion_reason')}")

    steps = data.get("steps", [])
    if steps:
        print(f"\nSteps executed: {len(steps)}")
        for step in steps:
            idx = step.get("step_index")
            action = step.get("action")
            plan = step.get("plan")
            behavior = step.get("behavior_fact_answer")
            print(f"\nStep {idx}:")
            print(f"  Plan: {plan}")
            print(f"  Action: {action}")
            if behavior:
                print(f"  Behavior Narrator: {behavior}")
    else:
        print("No steps recorded.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

