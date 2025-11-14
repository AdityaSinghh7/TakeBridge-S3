from __future__ import annotations

import json
from typing import Any, Dict


def parse_planner_command(text: str) -> Dict[str, Any]:
    """
    Parse planner LLM output into a structured command dict.

    Expected format (JSON):
        {
            "type": "tool" | "sandbox" | "finish",
            ...
        }
    """
    text = (text or "").strip()
    if not text:
        raise ValueError("Planner response was empty.")
    try:
        command = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("Planner response must be valid JSON.") from exc

    if not isinstance(command, dict):
        raise ValueError("Planner response must be a JSON object.")

    cmd_type = command.get("type")
    if cmd_type not in {"tool", "sandbox", "finish", "search"}:
        raise ValueError("Planner response missing 'type' or unsupported command.")
    _VALIDATORS[cmd_type](command)
    return command


def _ensure(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _validate_tool(command: Dict[str, Any]) -> None:
    provider = command.get("provider")
    tool = command.get("tool")
    payload = command.get("payload", {}) or {}
    _ensure(isinstance(provider, str) and provider.strip(), "Tool command requires non-empty 'provider'.")
    _ensure(isinstance(tool, str) and tool.strip(), "Tool command requires non-empty 'tool'.")
    _ensure(isinstance(payload, dict), "Tool command 'payload' must be an object.")
    command["provider"] = provider.strip()
    command["tool"] = tool.strip()
    command["payload"] = payload


def _validate_sandbox(command: Dict[str, Any]) -> None:
    code = command.get("code")
    _ensure(isinstance(code, str) and code.strip(), "Sandbox command requires non-empty 'code'.")
    command["code"] = code


def _validate_finish(command: Dict[str, Any]) -> None:
    summary = command.get("summary")
    if summary is not None:
        _ensure(isinstance(summary, str), "Finish command 'summary' must be a string.")


def _validate_search(command: Dict[str, Any]) -> None:
    query = command.get("query")
    _ensure(isinstance(query, str) and query.strip(), "Search command requires non-empty 'query'.")
    if "detail_level" in command:
        _ensure(
            isinstance(command["detail_level"], str),
            "Search command 'detail_level' must be a string.",
        )
    if "limit" in command:
        limit = command["limit"]
        _ensure(
            isinstance(limit, int) and 1 <= limit <= 50,
            "Search command 'limit' must be an integer between 1 and 50.",
        )


_VALIDATORS = {
    "tool": _validate_tool,
    "sandbox": _validate_sandbox,
    "finish": _validate_finish,
    "search": _validate_search,
}
