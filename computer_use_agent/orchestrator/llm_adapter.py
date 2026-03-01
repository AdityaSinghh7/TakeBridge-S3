from __future__ import annotations

import json
import logging
import uuid
from typing import Any, Dict, Iterable, List, Optional, Tuple

from langchain_core.messages import AIMessage
from langchain_core.tools import BaseTool

from shared.llm_client import LLMClient, extract_assistant_text

logger = logging.getLogger(__name__)


def _model_dump(obj: Any) -> Dict[str, Any]:
    if obj is None:
        return {}
    if isinstance(obj, dict):
        return dict(obj)
    if hasattr(obj, "model_dump") and callable(getattr(obj, "model_dump")):
        try:
            return obj.model_dump()
        except Exception:
            pass
    if hasattr(obj, "__dict__"):
        try:
            return {
                key: value
                for key, value in vars(obj).items()
                if not key.startswith("_")
            }
        except Exception:
            pass
    try:
        return dict(obj)  # type: ignore[arg-type]
    except Exception:
        return {"value": obj}


def _coerce_tool_args(raw_args: Any) -> Dict[str, Any]:
    if raw_args is None:
        return {}
    if isinstance(raw_args, dict):
        return raw_args
    if isinstance(raw_args, str):
        payload = raw_args.strip()
        if not payload:
            return {}
        try:
            loaded = json.loads(payload)
        except Exception:
            logger.warning("Failed to parse tool call arguments as JSON: %s", payload)
            return {}
        return loaded if isinstance(loaded, dict) else {}
    return {}


def extract_tool_calls_from_response(response: Any) -> List[Dict[str, Any]]:
    output_items = getattr(response, "output", None)
    if output_items is None and isinstance(response, dict):
        output_items = response.get("output")
    tool_calls: List[Dict[str, Any]] = []

    for item in output_items or []:
        item_dict = _model_dump(item)
        item_type = item_dict.get("type")
        if item_type not in {"function_call", "tool_call"}:
            continue
        name = item_dict.get("name")
        if not name and isinstance(item_dict.get("function"), dict):
            name = item_dict["function"].get("name")
        if not name:
            continue

        call_id = (
            item_dict.get("call_id")
            or item_dict.get("id")
            or str(uuid.uuid4())
        )
        raw_args = item_dict.get("arguments")
        if raw_args is None and isinstance(item_dict.get("function"), dict):
            raw_args = item_dict["function"].get("arguments")

        tool_calls.append(
            {
                "id": str(call_id),
                "name": str(name),
                "args": _coerce_tool_args(raw_args),
                "type": "tool_call",
            }
        )

    # Compatibility fallback for chat-completions shaped payloads.
    if tool_calls:
        return tool_calls

    choices = None
    if isinstance(response, dict):
        choices = response.get("choices")
    else:
        choices = getattr(response, "choices", None)
    if not choices:
        return []

    for choice in choices:
        choice_dict = _model_dump(choice)
        message = choice_dict.get("message") or choice_dict.get("delta") or {}
        for entry in message.get("tool_calls") or []:
            entry_dict = _model_dump(entry)
            function = entry_dict.get("function") or {}
            name = function.get("name")
            if not name:
                continue
            tool_calls.append(
                {
                    "id": str(entry_dict.get("id") or uuid.uuid4()),
                    "name": str(name),
                    "args": _coerce_tool_args(function.get("arguments")),
                    "type": "tool_call",
                }
            )
    return tool_calls


def convert_langchain_tools_to_responses_api(
    tools: Iterable[BaseTool],
) -> List[Dict[str, Any]]:
    payloads: List[Dict[str, Any]] = []
    for tool in tools:
        args_schema = getattr(tool, "args_schema", None)
        if args_schema is None:
            parameters: Dict[str, Any] = {"type": "object", "properties": {}}
        elif hasattr(args_schema, "model_json_schema"):
            parameters = args_schema.model_json_schema()
        elif hasattr(args_schema, "schema"):
            parameters = args_schema.schema()  # type: ignore[assignment]
        else:
            parameters = {"type": "object", "properties": {}}
        parameters.setdefault("type", "object")
        parameters.setdefault("properties", {})
        payloads.append(
            {
                "type": "function",
                "name": tool.name,
                "description": tool.description or "",
                "parameters": parameters,
            }
        )
    return payloads


class ToolCallingLLMAdapter:
    def __init__(self, engine_params: Dict[str, Any]) -> None:
        model = str(engine_params.get("model") or "o4-mini")
        reasoning_effort = str(engine_params.get("reasoning_effort") or "medium")
        reasoning_summary = engine_params.get("reasoning_summary")
        max_retries = engine_params.get("max_retries")

        self._max_output_tokens = engine_params.get("max_output_tokens")
        self._reasoning_effort = reasoning_effort
        self._reasoning_summary = reasoning_summary
        self._client = LLMClient(
            default_model=model,
            default_reasoning_effort=reasoning_effort,
            default_reasoning_summary=reasoning_summary,
            max_retries=max_retries if isinstance(max_retries, int) else None,
            provider=engine_params.get("engine_type"),
            base_url=engine_params.get("base_url"),
            api_key=engine_params.get("api_key"),
        )

    def generate_ai_message(
        self,
        *,
        messages: Iterable[Dict[str, Any]],
        tools: Iterable[BaseTool],
        cost_source: str,
        reasoning_effort: Optional[str] = None,
        max_output_tokens: Optional[int] = None,
    ) -> Tuple[AIMessage, Any]:
        tool_payloads = convert_langchain_tools_to_responses_api(tools)
        response = self._client.create_response(
            messages=list(messages),
            tools=tool_payloads,
            reasoning_effort=reasoning_effort or self._reasoning_effort,
            reasoning_summary=self._reasoning_summary,
            max_output_tokens=max_output_tokens or self._max_output_tokens,
            cost_source=cost_source,
        )
        assistant_text = extract_assistant_text(response) or ""
        tool_calls = extract_tool_calls_from_response(response)
        return AIMessage(content=assistant_text, tool_calls=tool_calls), response

