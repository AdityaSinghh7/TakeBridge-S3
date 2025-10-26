"""
oai_responses_wrapper.py

Thin, reusable wrapper around the OpenAI Responses API.
- Supports chat-style `messages` or raw `input` items.
- Pluggable tools / function-calling.
- Conversation state via `conversation` and `previous_response_id`.
- Reasoning controls: effort ("low" | "medium" | "high") and summaries ("auto" | "concise" | "detailed" | None).
- Utilities to pass back prior reasoning + tool items, and to extract assistant text.

Requires: openai>=1.0.0
"""

from __future__ import annotations

import os
import random
import time
from functools import lru_cache

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Literal, Optional, Sequence, Union

try:
    # Optional dependency; we won't hard-require it
    from dotenv import load_dotenv, find_dotenv  # type: ignore
except Exception:  # pragma: no cover
    load_dotenv = None
    find_dotenv = None

from openai import OpenAI
try:
    from openai import (
        APIConnectionError,
        APIError,
        APITimeoutError,
        APIStatusError,
        RateLimitError,
    )
except Exception:  # pragma: no cover
    try:
        from openai.error import OpenAIError as APIError  # type: ignore
    except Exception:  # pragma: no cover
        APIError = Exception  # type: ignore[assignment]
    APIConnectionError = APITimeoutError = APIStatusError = RateLimitError = Exception  # type: ignore[assignment]
from openai.types.responses import Response

Message = Dict[str, Any]
InputItem = Dict[str, Any]
Tool = Dict[str, Any]

ReasoningEffort = Literal["low", "medium", "high"]
ReasoningSummary = Optional[Literal["auto", "concise", "detailed"]]

DEFAULT_MAX_RETRIES = 3
DEFAULT_BACKOFF_BASE_SECONDS = 0.5
DEFAULT_BACKOFF_CAP_SECONDS = 8.0
DEFAULT_BACKOFF_JITTER_SECONDS = 0.25
_RETRYABLE_STATUS_CODES = {408, 409, 425, 429, 500, 502, 503, 504}


def _is_retryable_error(exc: Exception) -> bool:
    """
    Determine if the exception returned by the OpenAI client is retryable.
    Conservatively matches connection/timeouts + known transient status codes.
    """
    if isinstance(
        exc,
        (
            APIConnectionError,
            APITimeoutError,
            RateLimitError,
        ),
    ):
        return True
    if isinstance(exc, APIStatusError):
        status_code = getattr(exc, "status_code", None) or getattr(exc, "status", None)
        if isinstance(status_code, int) and status_code in _RETRYABLE_STATUS_CODES:
            return True
    if isinstance(exc, APIError):
        status_code = getattr(exc, "status_code", None) or getattr(exc, "status", None)
        if isinstance(status_code, int) and status_code in _RETRYABLE_STATUS_CODES:
            return True
        # Some APIError instances expose error.type (string) describing the failure kind.
        error_type = getattr(exc, "type", None)
        if isinstance(error_type, str) and any(
            keyword in error_type
            for keyword in ("timeout", "server_error", "connection_error")
        ):
            return True
    # Fallback: treat built-in transient network issues as retryable.
    if isinstance(exc, (TimeoutError, ConnectionError)):  # type: ignore[arg-type]
        return True
    return False


def _normalize_messages(messages: Iterable[Message]) -> List[Message]:
    """
    Ensure messages are in Responses API message shape:
    { "role": "system|user|assistant|developer|tool", "content": [ {type: "text", text: "..."} | ... ] }
    """
    normalized: List[Message] = []
    for message in messages:
        role = message.get("role")
        if not role:
            raise ValueError("Each message must include a 'role'.")
        content = message.get("content", "")
        if isinstance(content, str):
            content = [{"type": "text", "text": content}]
        normalized.append({"role": role, "content": content})
    return normalized


def _messages_to_input(messages: Iterable[Message]) -> List[InputItem]:
    """For convenience: the Responses API accepts `input`=messages directly."""
    return _normalize_messages(messages)


def extract_assistant_text(resp: Response) -> str:
    """
    Concatenate assistant output_text across message items.
    Returns "" if none.
    """
    text_chunks: List[str] = []
    for item in getattr(resp, "output", []) or []:
        if item.get("type") == "message" and item.get("role") == "assistant":
            for c in item.get("content", []):
                if c.get("type") in ("output_text", "text"):
                    if "text" in c:
                        text_chunks.append(c["text"])
    return "".join(text_chunks)


def extract_items_since_last_user(resp: Response) -> List[InputItem]:
    """
    Return all output items from `resp` that the docs recommend passing back on the next turn
    for best reasoning performance (reasoning items + any tool/function call + their outputs +
    the assistant message items). This is a pragmatic take: we include all `output` items.

    If you prefer to be selective, filter by item["type"] in:
      {"reasoning", "tool_call", "tool_result", "function_call", "function_call_output", "message"}
    """
    items = getattr(resp, "output", []) or []
    # Shallow copy to avoid accidental mutation
    return [dict(x) for x in items]


@dataclass
class ResponseSession:
    """
    Lightweight session helper you can hold per user/task.
    - conversation: Optional conversation id (Conversations API)
    - previous_response_id: last Responses API id, for `previous_response_id` chaining
    - carry_items: prior output items to replay (reasoning/tool/function items)
    """
    conversation: Optional[str] = None
    previous_response_id: Optional[str] = None
    carry_items: List[InputItem] = field(default_factory=list)

    def update_from(self, resp: Response) -> None:
        """Update session state after a call."""
        self.previous_response_id = resp.id  # always usable for chaining
        # Refresh carry_items to everything since last user message per docs guidance
        self.carry_items = extract_items_since_last_user(resp)


class OAIClient:
    """Reusable OpenAI client for issuing Responses API calls with sane defaults."""

    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        default_model: str = "o4-mini",
        default_reasoning_effort: ReasoningEffort = "medium",
        default_reasoning_summary: ReasoningSummary = None,  # e.g., "auto" if you always want summaries
        timeout: Optional[float] = None,
        base_url: Optional[str] = None,  # allow Azure/OpenRouter/self-hosted gateways
        default_tools: Optional[List[Tool]] = None,
        max_retries: int = DEFAULT_MAX_RETRIES,
        retry_backoff_base: float = DEFAULT_BACKOFF_BASE_SECONDS,
        retry_backoff_cap: float = DEFAULT_BACKOFF_CAP_SECONDS,
        retry_backoff_jitter: float = DEFAULT_BACKOFF_JITTER_SECONDS,
    ) -> None:
        if api_key is None:
            # Load OPENAI_API_KEY from env (optionally preloaded via respond_once)
            api_key = os.getenv("OPENAI_API_KEY")

        client_kwargs: Dict[str, Any] = {"api_key": api_key, "timeout": timeout}
        if base_url:
            client_kwargs["base_url"] = base_url
        self._client = OpenAI(**client_kwargs)
        self._default_model = default_model
        self._default_reasoning_effort = default_reasoning_effort
        self._default_reasoning_summary = default_reasoning_summary
        self._default_tools = default_tools or []
        self._max_retries = max(0, int(max_retries))
        base = max(0.0, float(retry_backoff_base))
        cap = max(base, float(retry_backoff_cap))
        self._retry_backoff_base = base
        self._retry_backoff_cap = cap
        self._retry_backoff_jitter = max(0.0, float(retry_backoff_jitter))

    @property
    def default_model(self) -> str:
        return self._default_model

    def create_response(
        self,
        *,
        # Core
        model: Optional[str] = None,
        messages: Optional[Iterable[Message]] = None,
        input: Optional[Union[InputItem, Sequence[InputItem], str]] = None,
        # Output / control
        max_output_tokens: Optional[int] = None,
        tools: Optional[List[Tool]] = None,
        # Conversation / chaining
        conversation: Optional[str] = None,
        previous_response_id: Optional[str] = None,
        # Reasoning controls
        reasoning_effort: Optional[ReasoningEffort] = None,
        reasoning_summary: ReasoningSummary = None,
        # Carry-forward reasoning + tool items
        carry_items: Optional[List[InputItem]] = None,
        # Retry controls
        max_retries: Optional[int] = None,
        retry_backoff_base: Optional[float] = None,
        retry_backoff_cap: Optional[float] = None,
        retry_backoff_jitter: Optional[float] = None,
        # Any other passthrough args (e.g., temperature, stop, metadata, store, ...)
        **kwargs: Any,
    ) -> Response:
        """
        Issue a Responses API request.

        You may provide either `messages` (chat-style) or raw `input`.
        For multi-turn with reasoning/tool calls:
          - Prefer passing `previous_response_id` OR
          - Include `carry_items` (e.g., from `extract_items_since_last_user()`).

        Args:
            model: model id, defaults to the client's default model.
            messages: chat-style messages; converted to `input` if provided.
            input: raw Responses API input items (string or item list).
            max_output_tokens: hard cap for generated tokens.
            tools: list of tool (function) specs.
            conversation: conversation id (Conversations API).
            previous_response_id: link to prior response for server-side replay.
            reasoning_effort: "low" | "medium" | "high" (default "medium").
            reasoning_summary: "auto" | "concise" | "detailed" | None. If None, omitted.
            carry_items: items to prepend (reasoning/tool/function items from prior turn).
            max_retries: number of retry attempts for retryable errors (defaults to client config).
            retry_backoff_base: starting backoff delay in seconds (defaults to client config).
            retry_backoff_cap: maximum backoff delay in seconds (defaults to client config).
            retry_backoff_jitter: random jitter (0..value) in seconds added to backoff (defaults to client config).
            **kwargs: forwarded to `client.responses.create(...)`.

        Returns:
            openai.types.responses.Response
        """
        if input is None and messages is None:
            raise ValueError("Either 'input' or 'messages' must be provided.")

        payload: Dict[str, Any] = {
            "model": model or self._default_model,
        }

        # Input assembly
        if input is not None:
            if isinstance(input, str):
                payload["input"] = input  # text-only
            else:
                payload["input"] = list(input)  # sequence of items
        else:
            payload["input"] = _messages_to_input(messages or [])

        # Optionally prepend carry-forward items (reasoning, tool calls, outputs, assistant msgs)
        if carry_items:
            # The recommended simple pattern is: prior output items + new user input.
            # We place them first so server sees them before the new user message.
            # (If you want the inverse ordering, adjust here.)
            new_input = []
            new_input.extend(carry_items)
            # Ensure we append the newly provided input
            if isinstance(payload["input"], list):
                new_input.extend(payload["input"])
            else:
                new_input.append(payload["input"])
            payload["input"] = new_input

        # Tools
        if tools is not None:
            payload["tools"] = tools
        elif self._default_tools:
            payload["tools"] = self._default_tools

        # Output caps
        if max_output_tokens is not None:
            payload["max_output_tokens"] = int(max_output_tokens)

        # Conversation + chaining
        if conversation:
            payload["conversation"] = conversation
        if previous_response_id:
            payload["previous_response_id"] = previous_response_id

        # Reasoning controls
        effort = reasoning_effort or self._default_reasoning_effort
        reasoning_obj: Dict[str, Any] = {"effort": effort}
        summary_value = (
            reasoning_summary
            if reasoning_summary is not None
            else self._default_reasoning_summary
        )
        if summary_value:
            reasoning_obj["summary"] = summary_value
        # Only include reasoning block if we have anything beyond defaults or you want to always send it.
        if reasoning_obj:
            payload["reasoning"] = reasoning_obj

        # Any passthrough params (temperature, stop, metadata, store, etc.)
        payload.update(kwargs)

        resolved_max_retries = (
            self._max_retries if max_retries is None else max(0, int(max_retries))
        )
        resolved_backoff_base = (
            self._retry_backoff_base
            if retry_backoff_base is None
            else max(0.0, float(retry_backoff_base))
        )
        resolved_backoff_cap = (
            self._retry_backoff_cap
            if retry_backoff_cap is None
            else max(resolved_backoff_base, float(retry_backoff_cap))
        )
        resolved_backoff_jitter = (
            self._retry_backoff_jitter
            if retry_backoff_jitter is None
            else max(0.0, float(retry_backoff_jitter))
        )

        attempt = 0
        while True:
            try:
                return self._client.responses.create(**payload)
            except Exception as exc:
                if not _is_retryable_error(exc) or attempt >= resolved_max_retries:
                    raise
                backoff_seconds = min(
                    resolved_backoff_cap,
                    resolved_backoff_base * (2**attempt),
                )
                if resolved_backoff_jitter:
                    backoff_seconds += random.uniform(0.0, resolved_backoff_jitter)
                time.sleep(backoff_seconds)
                attempt += 1

    # ---------- High-level conveniences ----------

    def respond_with_session(
        self,
        session: ResponseSession,
        *,
        model: Optional[str] = None,
        messages: Optional[Iterable[Message]] = None,
        input: Optional[Union[InputItem, Sequence[InputItem], str]] = None,
        tools: Optional[List[Tool]] = None,
        max_output_tokens: Optional[int] = None,
        reasoning_effort: Optional[ReasoningEffort] = None,
        reasoning_summary: ReasoningSummary = None,
        **kwargs: Any,
    ) -> Response:
        """
        Like `create_response`, but wires up `conversation`, `previous_response_id`,
        and `carry_items` from the provided `ResponseSession`. Also updates the session.
        """
        resp = self.create_response(
            model=model,
            messages=messages,
            input=input,
            tools=tools,
            max_output_tokens=max_output_tokens,
            conversation=session.conversation,
            previous_response_id=session.previous_response_id,
            carry_items=session.carry_items,
            reasoning_effort=reasoning_effort,
            reasoning_summary=reasoning_summary,
            **kwargs,
        )
        session.update_from(resp)
        return resp


def _maybe_load_env(dotenv_path: Optional[str] = None) -> None:
    """
    Load environment from a .env file if python-dotenv is available.
    If dotenv_path is None, uses find_dotenv() if present.
    If python-dotenv isn't installed, silently no-op.
    """
    if load_dotenv is None:
        return
    path = dotenv_path or (find_dotenv() if find_dotenv else None)
    if path:
        load_dotenv(path, override=False)


@lru_cache(maxsize=8)
def _get_client_singleton(
    *,
    default_model: str = "o4-mini",
    default_reasoning_effort: ReasoningEffort = "medium",
    default_reasoning_summary: ReasoningSummary = None,
    timeout: Optional[float] = None,
    base_url: Optional[str] = None,
    # default tools at client scope (rare; you can still pass per-call tools)
    default_tools_fingerprint: Optional[str] = None,
) -> OAIClient:
    """
    Cached singleton so repeated respond_once(...) calls don't rebuild the SDK client.
    default_tools_fingerprint: pass a stable string if you want a unique cache entry
    per default tool set (e.g., hash of the tools schema). Otherwise, leave None.
    """
    return OAIClient(
        default_model=default_model,
        default_reasoning_effort=default_reasoning_effort,
        default_reasoning_summary=default_reasoning_summary,
        timeout=timeout,
        base_url=base_url,
        # NOTE: default tools bound at client creation only if you also pass them below
        default_tools=None,
    )


def respond_once(
    *,
    # Core input
    messages: Optional[Iterable[Message]] = None,
    input: Optional[Union[InputItem, Sequence[InputItem], str]] = None,
    # Model + controls
    model: str = "o4-mini",
    max_output_tokens: Optional[int] = None,
    tools: Optional[List[Tool]] = None,
    # Reasoning controls
    reasoning_effort: ReasoningEffort = "medium",
    reasoning_summary: ReasoningSummary = None,
    # Optional conversation/chaining even without managed session
    conversation: Optional[str] = None,
    previous_response_id: Optional[str] = None,
    # Environment / client config
    dotenv_path: Optional[str] = None,  # load OPENAI_API_KEY from this .env (or auto-find)
    timeout: Optional[float] = None,
    base_url: Optional[str] = None,
    # Retry controls
    max_retries: Optional[int] = None,
    retry_backoff_base: Optional[float] = None,
    retry_backoff_cap: Optional[float] = None,
    retry_backoff_jitter: Optional[float] = None,
    # Any passthrough (temperature, stop, metadata, store, ...)
    **kwargs: Any,
) -> Response:
    """
    High-level one-shot Responses call:
      - Loads OPENAI_API_KEY from .env (if available) → env → SDK default.
      - Reuses a cached OpenAI client under the hood.
      - No ResponseSession required.
      - Applies exponential backoff retries for transient failures (configurable).

    Returns:
        openai.types.responses.Response
    """
    # Load env before constructing/using the client so OPENAI_API_KEY is present
    _maybe_load_env(dotenv_path)

    # Optional cache partitioning by base client behavior
    client = _get_client_singleton(
        default_model=model,
        default_reasoning_effort=reasoning_effort,
        default_reasoning_summary=reasoning_summary,
        timeout=timeout,
        base_url=base_url,
        default_tools_fingerprint=None,
    )

    # We still pass per-call settings explicitly so they apply even with a cached client
    return client.create_response(
        model=model,
        messages=messages,
        input=input,
        max_output_tokens=max_output_tokens,
        tools=tools,
        conversation=conversation,
        previous_response_id=previous_response_id,
        reasoning_effort=reasoning_effort,
        reasoning_summary=reasoning_summary,
        max_retries=max_retries,
        retry_backoff_base=retry_backoff_base,
        retry_backoff_cap=retry_backoff_cap,
        retry_backoff_jitter=retry_backoff_jitter,
        **kwargs,
    )
