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
    if cmd_type not in {"tool", "sandbox", "finish", "search", "fail"}:
        raise ValueError("Planner response missing 'type' or unsupported command.")
    reasoning = command.get("reasoning")
    if not isinstance(reasoning, str) or not reasoning.strip():
        raise ValueError("Planner command must include non-empty 'reasoning' string.")
    command["reasoning"] = reasoning.strip()
    _VALIDATORS[cmd_type](command)
    return command


def _ensure(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _validate_tool(command: Dict[str, Any]) -> None:
    tool_id = command.get("tool_id")
    server = command.get("server")
    args = command.get("args")

    provider = command.get("provider")
    tool = command.get("tool")
    payload = command.get("payload")

    if tool_id and server:
        _ensure(isinstance(tool_id, str) and tool_id.strip(), "Tool command requires non-empty 'tool_id'.")
        _ensure(isinstance(server, str) and server.strip(), "Tool command requires non-empty 'server'.")
        if args is None:
            args = {}
        _ensure(isinstance(args, dict), "Tool command 'args' must be an object.")
        command["tool_id"] = tool_id.strip()
        command["server"] = server.strip()
        command["args"] = args
        return

    _ensure(isinstance(provider, str) and provider.strip(), "Tool command requires non-empty 'provider'.")
    _ensure(isinstance(tool, str) and tool.strip(), "Tool command requires non-empty 'tool'.")
    if payload is None:
        payload = {}
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


def _validate_fail(command: Dict[str, Any]) -> None:
    reason = command.get("reason")
    _ensure(
        isinstance(reason, str) and reason.strip(),
        "Fail command requires non-empty 'reason'.",
    )


_VALIDATORS = {
    "tool": _validate_tool,
    "sandbox": _validate_sandbox,
    "finish": _validate_finish,
    "search": _validate_search,
    "fail": _validate_fail,
}
