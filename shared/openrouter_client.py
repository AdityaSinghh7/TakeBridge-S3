"""
openrouter_client.py

Thin wrapper around the OpenRouter Chat Completions API (OpenAI-compatible).
"""

from __future__ import annotations

import base64
import logging
import os
import random
import time
from contextlib import nullcontext
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Dict, Iterable, List, Literal, Optional, Sequence, Union

from shared.run_context import RUN_LOG_ID

logger = logging.getLogger(__name__)

try:
    from dotenv import load_dotenv, find_dotenv  # type: ignore
except Exception:  # pragma: no cover
    load_dotenv = None
    find_dotenv = None

try:
    from openai import OpenAI
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

    class _MissingOpenAI:  # pragma: no cover
        def __init__(self, *args, **kwargs):
            raise RuntimeError(
                "The 'openai' package is required to instantiate OpenRouterClient. "
                "Install openai>=1.0 to enable OpenRouter calls."
            )

    OpenAI = _MissingOpenAI  # type: ignore

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
_OPENROUTER_QWEN3_MODEL = "qwen/qwen3-vl-235b-a22b-instruct"
_ENABLE_OPENROUTER_PROVIDER_ONLY = False
_OPENROUTER_PROVIDER_ONLY = ["alibaba"]


def _is_retryable_error(exc: Exception) -> bool:
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
        error_type = getattr(exc, "type", None)
        if isinstance(error_type, str) and any(
            keyword in error_type
            for keyword in ("timeout", "server_error", "connection_error")
        ):
            return True
    if isinstance(exc, (TimeoutError, ConnectionError)):  # type: ignore[arg-type]
        return True
    return False


def _extract_text_from_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        chunks: List[str] = []
        for item in content:
            text = _extract_text_from_content(item)
            if text:
                chunks.append(text)
        return "".join(chunks)
    if isinstance(content, dict):
        item_type = content.get("type")
        if item_type in {"text", "input_text", "output_text"}:
            return str(content.get("text", "") or "")
        if item_type in {"image_url", "input_image", "output_image", "image"}:
            return ""
        if "image_url" in content or "image" in content:
            return ""
        if "text" in content:
            return str(content.get("text", "") or "")
        return ""
    return ""


def _provider_only_for_model(model_name: str) -> list[str] | None:
    if not _ENABLE_OPENROUTER_PROVIDER_ONLY:
        return None
    env_model = (os.getenv("OPENROUTER_MODEL") or "").strip()
    if env_model and model_name == env_model:
        return _OPENROUTER_PROVIDER_ONLY
    if model_name == _OPENROUTER_QWEN3_MODEL:
        return _OPENROUTER_PROVIDER_ONLY
    return None


def _guess_image_mime(image_bytes: bytes) -> str:
    if image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if image_bytes[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if image_bytes[:6] in {b"GIF87a", b"GIF89a"}:
        return "image/gif"
    if image_bytes[:4] == b"RIFF" and image_bytes[8:12] == b"WEBP":
        return "image/webp"
    return "image/png"


def _normalize_image_item(item: Dict[str, Any]) -> Dict[str, Any]:
    image_url = item.get("image_url") or item.get("imageUrl") or item.get("image")
    detail = item.get("detail")
    if isinstance(image_url, dict):
        detail = detail or image_url.get("detail")
        url = image_url.get("url")
    else:
        url = image_url
    if isinstance(url, (bytes, bytearray)):
        raw = bytes(url)
        mime_type = _guess_image_mime(raw)
        encoded = base64.b64encode(raw).decode("ascii")
        url = f"data:{mime_type};base64,{encoded}"
    if not isinstance(url, str) or not url:
        raise ValueError("image content must include a non-empty url.")
    payload: Dict[str, Any] = {"url": url}
    if detail:
        payload["detail"] = detail
    return {"type": "image_url", "image_url": payload}


def _normalize_content_item(item: Dict[str, Any]) -> Dict[str, Any]:
    item_type = item.get("type")

    if item_type in {"image_url", "input_image", "output_image", "image"}:
        return _normalize_image_item(item)

    if "image_url" in item or "imageUrl" in item or "image" in item:
        return _normalize_image_item(item)

    if item_type in {"text", "input_text", "output_text"} or "text" in item:
        return {"type": "text", "text": item.get("text", "") or ""}

    return {"type": "text", "text": _extract_text_from_content(item)}


def _normalize_content(content: Any) -> Union[str, List[Dict[str, Any]]]:
    if isinstance(content, str):
        return content
    if isinstance(content, dict):
        return [_normalize_content_item(content)]
    if isinstance(content, list):
        normalized: List[Dict[str, Any]] = []
        for item in content:
            if isinstance(item, str):
                normalized.append({"type": "text", "text": item})
            elif isinstance(item, dict):
                normalized.append(_normalize_content_item(item))
            else:
                normalized.append({"type": "text", "text": str(item)})
        return normalized
    return str(content)


def _normalize_messages_for_chat(messages: Iterable[Message]) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    for message in messages:
        role = message.get("role")
        if not role:
            raise ValueError("Each message must include a 'role'.")
        if role == "developer":
            role = "system"
        content = message.get("content", "")
        normalized.append({"role": role, "content": _normalize_content(content)})
    return normalized


def _coerce_input_to_messages(
    input_value: Union[InputItem, Sequence[InputItem], str]
) -> List[Dict[str, Any]]:
    if isinstance(input_value, str):
        return [{"role": "user", "content": input_value}]
    if isinstance(input_value, dict):
        if "role" in input_value:
            return _normalize_messages_for_chat([input_value])
        return [{"role": "user", "content": _normalize_content(input_value)}]
    if isinstance(input_value, list):
        if all(isinstance(item, dict) and "role" in item for item in input_value):
            return _normalize_messages_for_chat(input_value)
        return [{"role": "user", "content": _normalize_content(input_value)}]
    return [{"role": "user", "content": str(input_value)}]


def _messages_contain_json(messages: Iterable[Dict[str, Any]]) -> bool:
    for message in messages:
        text = _extract_text_from_content(message.get("content", ""))
        if "json" in text.lower():
            return True
    return False


def _ensure_json_instruction(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if _messages_contain_json(messages):
        return messages
    reminder = (
        "Respond in JSON only. Use the exact schema already provided. "
        'Example JSON: {"ok": true}'
    )
    return [{"role": "system", "content": reminder}, *messages]


def _maybe_load_env(dotenv_path: Optional[str] = None) -> None:
    if load_dotenv is None:
        return
    path = dotenv_path or (find_dotenv() if find_dotenv else None)
    if path:
        load_dotenv(path, override=False)


def _coerce_usage(usage: Any) -> Optional[Dict[str, Any]]:
    if usage is None:
        return None
    if isinstance(usage, dict):
        return usage
    if hasattr(usage, "model_dump") and callable(getattr(usage, "model_dump")):
        try:
            return usage.model_dump()  # type: ignore[call-arg]
        except Exception:
            pass
    if hasattr(usage, "__dict__"):
        return {k: v for k, v in vars(usage).items() if not k.startswith("_")}
    return None


def _default_extra_headers() -> Dict[str, str]:
    headers: Dict[str, str] = {}
    referer = os.getenv("OPENROUTER_HTTP_REFERER") or os.getenv("OPENROUTER_REFERER")
    title = os.getenv("OPENROUTER_TITLE")
    if referer:
        headers["HTTP-Referer"] = referer
    if title:
        headers["X-Title"] = title
    return headers


@dataclass
class OpenRouterResponse:
    content: str
    model: str
    usage: Optional[Dict[str, Any]] = None
    id: Optional[str] = None
    choices: List[Dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.choices:
            self.choices = [
                {"message": {"role": "assistant", "content": self.content}}
            ]

    def model_dump(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "model": self.model,
            "usage": self.usage,
            "choices": self.choices,
        }


class OpenRouterClient:
    """Reusable OpenRouter client for issuing chat completion calls."""

    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        default_model: str = "qwen/qwen3-vl-235b-a22b-instruct",
        default_reasoning_effort: ReasoningEffort = "medium",
        default_reasoning_summary: ReasoningSummary = None,
        timeout: Optional[float] = None,
        base_url: Optional[str] = None,
        default_tools: Optional[List[Tool]] = None,
        max_retries: int = DEFAULT_MAX_RETRIES,
        retry_backoff_base: float = DEFAULT_BACKOFF_BASE_SECONDS,
        retry_backoff_cap: float = DEFAULT_BACKOFF_CAP_SECONDS,
        retry_backoff_jitter: float = DEFAULT_BACKOFF_JITTER_SECONDS,
    ) -> None:
        if api_key is None:
            api_key = os.getenv("OPENROUTER_API_KEY")
        client_kwargs: Dict[str, Any] = {"api_key": api_key, "timeout": timeout}
        resolved_base_url = (
            base_url
            or os.getenv("OPENROUTER_BASE_URL")
            or "https://openrouter.ai/api/v1"
        )
        if resolved_base_url:
            client_kwargs["base_url"] = resolved_base_url
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
        self._extra_headers = _default_extra_headers()

    @property
    def default_model(self) -> str:
        return self._default_model

    def create_response(
        self,
        *,
        model: Optional[str] = None,
        messages: Optional[Iterable[Message]] = None,
        input: Optional[Union[InputItem, Sequence[InputItem], str]] = None,
        max_output_tokens: Optional[int] = None,
        tools: Optional[List[Tool]] = None,
        conversation: Optional[str] = None,
        previous_response_id: Optional[str] = None,
        reasoning_effort: Optional[ReasoningEffort] = None,
        reasoning_summary: ReasoningSummary = None,
        carry_items: Optional[List[InputItem]] = None,
        max_retries: Optional[int] = None,
        retry_backoff_base: Optional[float] = None,
        retry_backoff_cap: Optional[float] = None,
        retry_backoff_jitter: Optional[float] = None,
        stream: bool = False,
        **kwargs: Any,
    ) -> Any:
        if input is None and messages is None:
            raise ValueError("Either 'input' or 'messages' must be provided.")
        stream = bool(stream or kwargs.pop("stream", False))

        if input is not None:
            normalized_messages = _coerce_input_to_messages(input)
        else:
            normalized_messages = _normalize_messages_for_chat(messages or [])

        response_format = kwargs.pop("response_format", None)
        text_param = kwargs.pop("text", None)
        if response_format is None and isinstance(text_param, dict):
            format_payload = text_param.get("format", text_param)
            if isinstance(format_payload, dict) and format_payload.get("type") == "json_object":
                response_format = {"type": "json_object"}

        if isinstance(response_format, dict) and response_format.get("type") == "json_object":
            normalized_messages = _ensure_json_instruction(normalized_messages)

        kwargs.pop("cost_source", None)

        extra_headers = kwargs.pop("extra_headers", None) or {}
        if self._extra_headers:
            extra_headers = {**self._extra_headers, **extra_headers}

        model_name = model or self._default_model
        payload: Dict[str, Any] = {
            "model": model_name,
            "messages": normalized_messages,
        }

        if max_output_tokens is not None:
            payload["max_tokens"] = int(max_output_tokens)
        if tools is not None:
            payload["tools"] = tools
        elif self._default_tools:
            payload["tools"] = self._default_tools
        if response_format is not None:
            payload["response_format"] = response_format
        if extra_headers:
            payload["extra_headers"] = extra_headers

        extra_body = kwargs.pop("extra_body", None)
        provider_only = _provider_only_for_model(model_name)
        if provider_only and isinstance(extra_body, dict):
            if "provider" not in extra_body:
                extra_body = {**extra_body, "provider": {"only": provider_only}}
        elif provider_only and extra_body is None:
            extra_body = {"provider": {"only": provider_only}}
        if extra_body is not None:
            payload["extra_body"] = extra_body

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
                run_id = RUN_LOG_ID.get()
                logger.info(
                    "openrouter.request.start",
                    extra={
                        "model": payload.get("model"),
                        "stream": bool(stream),
                        "max_output_tokens": payload.get("max_tokens"),
                        "attempt": attempt + 1,
                        "cost_source": kwargs.get("cost_source"),
                        "run_id": run_id,
                    },
                )
                if stream:
                    stream_options = payload.pop("stream_options", None)
                    if stream_options is None:
                        payload["stream_options"] = {"include_usage": True}
                    return self._client.chat.completions.create(
                        **payload,
                        stream=True,
                    )
                return self._client.chat.completions.create(**payload)
            except Exception as exc:
                logger.warning(
                    "openrouter.request.retry",
                    extra={
                        "model": payload.get("model"),
                        "attempt": attempt + 1,
                        "max_retries": resolved_max_retries + 1,
                        "error": str(exc),
                        "run_id": RUN_LOG_ID.get(),
                    },
                )
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

    def stream_response(
        self,
        *,
        event_handler: Optional[Any] = None,
        **kwargs: Any,
    ) -> OpenRouterResponse:
        stream_obj = self.create_response(stream=True, **kwargs)
        context_manager = (
            stream_obj
            if hasattr(stream_obj, "__enter__") and hasattr(stream_obj, "__exit__")
            else nullcontext(stream_obj)
        )
        chunks: List[str] = []
        usage: Optional[Dict[str, Any]] = None
        model_name = kwargs.get("model") or self._default_model
        with context_manager as active_stream:
            for event in active_stream:
                try:
                    choices = getattr(event, "choices", None) or []
                    if choices:
                        delta = getattr(choices[0], "delta", None) or getattr(
                            choices[0], "message", None
                        )
                        if delta is not None:
                            content = getattr(delta, "content", None)
                            if isinstance(content, str) and content:
                                chunks.append(content)
                                if event_handler:
                                    event_handler(
                                        {
                                            "type": "response.output_text.delta",
                                            "delta": {"text": content},
                                        }
                                    )
                    event_usage = _coerce_usage(getattr(event, "usage", None))
                    if event_usage:
                        usage = event_usage
                    model_name = getattr(event, "model", model_name) or model_name
                except Exception:  # pragma: no cover
                    continue
        final_text = "".join(chunks)
        response = OpenRouterResponse(
            content=final_text,
            model=model_name,
            usage=usage,
        )
        if event_handler:
            try:
                event_handler(
                    {
                        "type": "response.completed",
                        "response": response,
                    }
                )
            except Exception:  # pragma: no cover
                pass
        return response


@lru_cache(maxsize=8)
def _get_client_singleton(
    *,
    default_model: str = "qwen/qwen3-vl-235b-a22b-instruct",
    timeout: Optional[float] = None,
    base_url: Optional[str] = None,
) -> OpenRouterClient:
    return OpenRouterClient(
        default_model=default_model,
        timeout=timeout,
        base_url=base_url,
    )


def respond_once(
    *,
    messages: Optional[Iterable[Message]] = None,
    input: Optional[Union[InputItem, Sequence[InputItem], str]] = None,
    model: str = "qwen/qwen3-vl-235b-a22b-instruct",
    max_output_tokens: Optional[int] = None,
    tools: Optional[List[Tool]] = None,
    reasoning_effort: ReasoningEffort = "medium",
    reasoning_summary: ReasoningSummary = None,
    conversation: Optional[str] = None,
    previous_response_id: Optional[str] = None,
    dotenv_path: Optional[str] = None,
    timeout: Optional[float] = None,
    base_url: Optional[str] = None,
    max_retries: Optional[int] = None,
    retry_backoff_base: Optional[float] = None,
    retry_backoff_cap: Optional[float] = None,
    retry_backoff_jitter: Optional[float] = None,
    **kwargs: Any,
) -> Any:
    _maybe_load_env(dotenv_path)
    client = _get_client_singleton(
        default_model=model,
        timeout=timeout,
        base_url=base_url,
    )
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


def get_client(
    *,
    api_key: Optional[str] = None,
    timeout: Optional[float] = None,
    base_url: Optional[str] = None,
) -> OpenAI:
    if api_key is None:
        api_key = os.getenv("OPENROUTER_API_KEY")
    client_kwargs: Dict[str, Any] = {"api_key": api_key}
    if timeout is not None:
        client_kwargs["timeout"] = timeout
    resolved_base_url = (
        base_url or os.getenv("OPENROUTER_BASE_URL") or "https://openrouter.ai/api/v1"
    )
    if resolved_base_url is not None:
        client_kwargs["base_url"] = resolved_base_url
    return OpenAI(**client_kwargs)
