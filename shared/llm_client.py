"""
llm_client.py

Provider-agnostic LLM facade that routes to OpenAI, DeepSeek (optionally via Baseten),
or OpenRouter based on env knobs.
"""

from __future__ import annotations

import base64
import concurrent.futures
import json
import logging
import os
import threading
import time
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Union

from shared.baseten_client import BasetenClient
from shared.deepseek_client import DeepSeekClient
from shared.llm_defaults import get_default_llm_timeout
from shared.openrouter_client import OpenRouterClient
from shared.oai_client import OAIClient as OpenAIClient
from shared.oai_client import extract_assistant_text as _extract_openai_text
from shared.llm_request_registry import clear_request, register_request
from shared.run_context import RUN_LOG_ID

logger = logging.getLogger(__name__)

Message = Dict[str, Any]
InputItem = Dict[str, Any]
Tool = Dict[str, Any]

try:
    from dotenv import load_dotenv, find_dotenv  # type: ignore
except Exception:  # pragma: no cover
    load_dotenv = None
    find_dotenv = None


def _maybe_load_env(dotenv_path: Optional[str] = None) -> None:
    if load_dotenv is None:
        return
    path = dotenv_path or (find_dotenv() if find_dotenv else None)
    if path:
        load_dotenv(path, override=False)


_LLM_LOG_LOCK = threading.Lock()
_LLM_CANCEL_POLL_SECONDS = 1.0
_LLM_RETRY_SENTINEL = object()


class LLMRequestCancelled(RuntimeError):
    pass


def _llm_log_enabled() -> bool:
    return os.getenv("LLM_LOG_ENABLED", "1").strip().lower() in {"1", "true", "yes", "on"}


def _baseten_enabled_for_deepseek() -> bool:
    return os.getenv("DEEPSEEK_BASETEN_ENABLED", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _baseten_default_model() -> str:
    baseten_model = os.getenv("BASETEN_MODEL")
    if baseten_model:
        return str(baseten_model)
    candidate = os.getenv("DEEPSEEK_MODEL") or os.getenv("LLM_MODEL")
    if candidate:
        candidate_value = str(candidate)
        if candidate_value.startswith("deepseek-") and "/" not in candidate_value:
            return "deepseek-ai/DeepSeek-V3.2"
        return candidate_value
    return "deepseek-ai/DeepSeek-V3.2"


def _sanitize_run_id(value: Optional[str]) -> str:
    if not value:
        return "unknown"
    return "".join(ch for ch in value if ch.isalnum() or ch in {"-", "_"}) or "unknown"


def _llm_log_path(run_id: Optional[str]) -> Path:
    log_dir = Path(os.getenv("LLM_LOG_DIR", "logs/llm")).expanduser()
    safe_run_id = _sanitize_run_id(run_id)
    return log_dir / f"llm-{safe_run_id}.jsonl"


def _compact_dict(data: Dict[str, Any]) -> Dict[str, Any]:
    return {key: value for key, value in data.items() if value is not None}


def _llm_pretty_log_path(run_id: Optional[str]) -> Path:
    return _llm_log_path(run_id).with_suffix(".log")


def _json_safe(value: Any, _seen: Optional[set[int]] = None) -> Any:
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, bytes):
        return {
            "__type__": "bytes",
            "base64": base64.b64encode(value).decode("ascii"),
        }
    if isinstance(value, bytearray):
        return {
            "__type__": "bytes",
            "base64": base64.b64encode(bytes(value)).decode("ascii"),
        }
    if isinstance(value, Path):
        return str(value)
    if _seen is None:
        _seen = set()
    value_id = id(value)
    if value_id in _seen:
        return "<circular>"
    _seen.add(value_id)
    if isinstance(value, dict):
        return {str(key): _json_safe(val, _seen) for key, val in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item, _seen) for item in value]
    if hasattr(value, "model_dump") and callable(getattr(value, "model_dump")):
        try:
            return _json_safe(value.model_dump(), _seen)  # type: ignore[call-arg]
        except Exception:
            pass
    if hasattr(value, "__dict__"):
        try:
            return _json_safe(
                {k: v for k, v in vars(value).items() if not k.startswith("_")},
                _seen,
            )
        except Exception:
            pass
    return str(value)


def _response_payload(response: Any) -> Any:
    if response is None:
        return None
    if hasattr(response, "model_dump") and callable(getattr(response, "model_dump")):
        try:
            return response.model_dump()
        except Exception:
            pass
    if isinstance(response, dict):
        return response
    if hasattr(response, "__dict__"):
        try:
            return {k: v for k, v in vars(response).items() if not k.startswith("_")}
        except Exception:
            pass
    return {"value": str(response)}


def _write_llm_log(entry: Dict[str, Any]) -> None:
    if not _llm_log_enabled():
        return
    try:
        run_id = entry.get("run_id")
        path = _llm_log_path(run_id)
        pretty_path = _llm_pretty_log_path(run_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(entry, ensure_ascii=True)
        with _LLM_LOG_LOCK:
            with open(path, "a", encoding="utf-8") as handle:
                handle.write(line + "\n")
            _write_llm_log_pretty(pretty_path, entry)
    except Exception:
        pass


def _write_llm_log_pretty(path: Path, entry: Dict[str, Any]) -> None:
    ts = entry.get("ts", "")
    requested_provider = entry.get("requested_provider")
    provider = entry.get("provider")
    requested_model = entry.get("requested_model")
    response_model = entry.get("response_model")
    route_reason = entry.get("route_reason")
    stream = entry.get("stream")
    duration_ms = entry.get("duration_ms")
    error = entry.get("error")

    request = entry.get("request") or {}
    messages = request.get("messages")
    input_payload = request.get("input")
    params = request.get("params")

    response_text = entry.get("response_text") or ""
    response_payload = entry.get("response")

    with open(path, "a", encoding="utf-8") as handle:
        handle.write(f"=== LLM CALL {ts} ===\n")
        handle.write(f"run_id: {entry.get('run_id')}\n")
        handle.write(f"provider: {provider} (requested: {requested_provider})\n")
        handle.write(f"model: {response_model or requested_model}\n")
        if route_reason:
            handle.write(f"route_reason: {route_reason}\n")
        handle.write(f"stream: {stream}\n")
        if duration_ms is not None:
            handle.write(f"duration_ms: {duration_ms}\n")

        if messages:
            handle.write("\nREQUEST_MESSAGES_TEXT:\n")
            for idx, msg in enumerate(messages):
                role = msg.get("role") if isinstance(msg, dict) else None
                content = msg.get("content") if isinstance(msg, dict) else msg
                text = _extract_text_from_content(content)
                handle.write(f"[{idx}] role={role}\n")
                if text:
                    handle.write(text + "\n")
                else:
                    handle.write("<no_text>\n")

        if input_payload is not None:
            handle.write("\nREQUEST_INPUT_RAW:\n")
            handle.write(json.dumps(input_payload, ensure_ascii=True, indent=2))
            handle.write("\n")

        if params:
            handle.write("\nREQUEST_PARAMS:\n")
            handle.write(json.dumps(params, ensure_ascii=True, indent=2))
            handle.write("\n")

        handle.write("\nRESPONSE_TEXT:\n")
        if response_text:
            handle.write(response_text + "\n")
        else:
            handle.write("<empty>\n")

        if error:
            handle.write("\nERROR:\n")
            handle.write(json.dumps(error, ensure_ascii=True, indent=2))
            handle.write("\n")

        handle.write("\n")


def _build_request_log(
    *,
    messages: Optional[Iterable[Message]],
    input: Optional[Union[InputItem, Sequence[InputItem], str]],
    params: Dict[str, Any],
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    request_params = _compact_dict(params)
    if extra:
        request_params["extra"] = extra
    return {
        "messages": messages,
        "input": input,
        "params": request_params,
    }


def _normalize_provider(provider: Optional[str]) -> str:
    value = (provider or os.getenv("LLM_PROVIDER", "openai")).strip().lower()
    if value in {"oai", "openai", "open-ai"}:
        return "openai"
    if value in {"deepseek", "deep-seek"}:
        return "deepseek"
    if value in {"openrouter", "open-router", "open_router"}:
        return "openrouter"
    raise ValueError(
        f"Unsupported LLM_PROVIDER '{value}'. Use 'openai', 'deepseek', or 'openrouter'."
    )


def _default_model_for_provider(provider: str) -> str:
    if provider == "deepseek":
        if _baseten_enabled_for_deepseek():
            return _baseten_default_model()
        candidate = os.getenv("DEEPSEEK_MODEL") or os.getenv("LLM_MODEL") or "deepseek-reasoner"
        if not str(candidate).startswith("deepseek-"):
            return "deepseek-reasoner"
        return str(candidate)
    if provider == "openrouter":
        candidate = os.getenv("OPENROUTER_MODEL") or "qwen/qwen3-vl-235b-a22b-instruct"
        if str(candidate).startswith("deepseek-"):
            return "qwen/qwen3-vl-235b-a22b-instruct"
        return str(candidate)
    candidate = os.getenv("LLM_MODEL") or "o4-mini"
    if str(candidate).startswith("deepseek-"):
        return "o4-mini"
    return str(candidate)


def _resolve_model(provider: str, model: Optional[str]) -> str:
    if model is None:
        return _default_model_for_provider(provider)
    model_value = str(model)
    if provider == "deepseek":
        if _baseten_enabled_for_deepseek():
            if "/" not in model_value:
                return _baseten_default_model()
            return model_value
        if not model_value.startswith("deepseek-"):
            return "deepseek-reasoner"
        return model_value
    if provider == "openrouter":
        if model_value.startswith("deepseek-"):
            return _default_model_for_provider("openrouter")
        return model_value
    if model_value.startswith("deepseek-"):
        return _default_model_for_provider("openai")
    return model_value


def _extract_text_from_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        chunks: List[str] = []
        for item in content:
            chunks.append(_extract_text_from_content(item))
        return "".join(chunk for chunk in chunks if chunk)
    if isinstance(content, dict):
        if "text" in content:
            return str(content.get("text") or "")
        return ""
    return ""


def _content_has_image(content: Any) -> bool:
    if isinstance(content, dict):
        item_type = content.get("type")
        if item_type in {"image_url", "input_image", "output_image", "image"}:
            return True
        if "image_url" in content or "image" in content:
            return True
        return False
    if isinstance(content, list):
        return any(_content_has_image(item) for item in content)
    return False


def _messages_have_images(messages: Iterable[Message]) -> bool:
    for message in messages:
        if _content_has_image(message.get("content", "")):
            return True
    return False


def _input_has_images(input_value: Any) -> bool:
    if isinstance(input_value, list):
        if all(isinstance(item, dict) and "role" in item for item in input_value):
            return _messages_have_images(input_value)
        return _content_has_image(input_value)
    if isinstance(input_value, dict):
        if "role" in input_value:
            return _messages_have_images([input_value])
        return _content_has_image(input_value)
    return False


def _extract_chat_completion_text(response: Any) -> str:
    choices = None
    if isinstance(response, dict):
        choices = response.get("choices")
    if choices is None:
        choices = getattr(response, "choices", None)
    if not choices:
        return ""
    chunks: List[str] = []
    for choice in choices:
        message = None
        if isinstance(choice, dict):
            message = choice.get("message") or choice.get("delta")
        else:
            message = getattr(choice, "message", None) or getattr(choice, "delta", None)
        if message is None:
            continue
        if isinstance(message, dict):
            content = message.get("content")
        else:
            content = getattr(message, "content", None)
        if content is None:
            continue
        chunks.append(_extract_text_from_content(content))
    return "".join(chunks)


def extract_assistant_text(response: Any) -> str:
    if response is None:
        return ""
    try:
        text = _extract_openai_text(response)
        if text:
            return text
    except Exception:
        pass
    text = _extract_chat_completion_text(response)
    if text:
        return text
    fallback = getattr(response, "output_text", None) or getattr(response, "text", None)
    if isinstance(fallback, str):
        return fallback
    return ""


class LLMClient:
    """Provider-agnostic client that routes to OpenAI or DeepSeek based on env."""

    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        default_model: Optional[str] = None,
        default_reasoning_effort: str = "medium",
        default_reasoning_summary: Optional[str] = None,
        timeout: Optional[float] = None,
        base_url: Optional[str] = None,
        default_tools: Optional[List[Tool]] = None,
        max_retries: Optional[int] = None,
        retry_backoff_base: Optional[float] = None,
        retry_backoff_cap: Optional[float] = None,
        retry_backoff_jitter: Optional[float] = None,
        provider: Optional[str] = None,
    ) -> None:
        if timeout is None:
            timeout = get_default_llm_timeout()
        self._provider = _normalize_provider(provider)
        self._fallback_provider = os.getenv("LLM_FALLBACK_PROVIDER")
        self._fallback_provider = (
            _normalize_provider(self._fallback_provider)
            if self._fallback_provider
            else None
        )
        self._image_provider = os.getenv("LLM_IMAGE_PROVIDER")
        self._image_provider = (
            _normalize_provider(self._image_provider)
            if self._image_provider
            else None
        )
        self._default_model_raw = default_model or _default_model_for_provider(self._provider)
        self._default_model = _resolve_model(self._provider, self._default_model_raw)
        self._timeout = timeout
        provider_kwargs: Dict[str, Any] = {
            "api_key": api_key,
            "default_model": self._default_model,
            "default_reasoning_effort": default_reasoning_effort,
            "default_reasoning_summary": default_reasoning_summary,
            "timeout": timeout,
            "base_url": base_url,
            "default_tools": default_tools,
        }
        if max_retries is not None:
            provider_kwargs["max_retries"] = max_retries
        if retry_backoff_base is not None:
            provider_kwargs["retry_backoff_base"] = retry_backoff_base
        if retry_backoff_cap is not None:
            provider_kwargs["retry_backoff_cap"] = retry_backoff_cap
        if retry_backoff_jitter is not None:
            provider_kwargs["retry_backoff_jitter"] = retry_backoff_jitter
        self._client = self._build_provider_client(
            provider=self._provider,
            **provider_kwargs,
        )
        self._fallback_client = None
        self._image_client = None

    @property
    def default_model(self) -> str:
        return self._default_model

    def _build_provider_client(self, *, provider: str, **kwargs: Any) -> Any:
        if provider == "openai":
            return OpenAIClient(**kwargs)
        if provider == "deepseek":
            if _baseten_enabled_for_deepseek():
                return BasetenClient(**kwargs)
            return DeepSeekClient(**kwargs)
        if provider == "openrouter":
            return OpenRouterClient(**kwargs)
        raise ValueError(f"Unsupported provider '{provider}'.")

    def _get_fallback_client(self) -> Optional[Any]:
        if not self._fallback_provider:
            return None
        if self._fallback_client is None:
            self._fallback_client = self._build_provider_client(
                provider=self._fallback_provider,
                default_model=_resolve_model(self._fallback_provider, self._default_model_raw),
                default_reasoning_effort="medium",
                default_reasoning_summary=None,
                timeout=self._timeout,
            )
        return self._fallback_client

    def _get_image_client(self) -> Optional[Any]:
        if not self._image_provider:
            return None
        if self._image_client is None:
            self._image_client = self._build_provider_client(
                provider=self._image_provider,
                default_model=_resolve_model(self._image_provider, self._default_model_raw),
                default_reasoning_effort="medium",
                default_reasoning_summary=None,
                timeout=self._timeout,
            )
        return self._image_client

    def _log_llm_call(
        self,
        *,
        requested_provider: str,
        provider: str,
        requested_model: str,
        request: Dict[str, Any],
        response: Any = None,
        error: Optional[Exception] = None,
        route_reason: Optional[str] = None,
        duration_ms: Optional[float] = None,
        stream: bool = False,
    ) -> None:
        if not _llm_log_enabled():
            return
        run_id = RUN_LOG_ID.get() or os.getenv("RUN_LOG_ID")
        entry: Dict[str, Any] = {
            "ts": datetime.utcnow().isoformat() + "Z",
            "run_id": run_id,
            "requested_provider": requested_provider,
            "provider": provider,
            "requested_model": requested_model,
            "route_reason": route_reason,
            "stream": stream,
            "duration_ms": round(float(duration_ms), 2) if duration_ms is not None else None,
            "request": request,
        }
        if response is not None:
            entry["response_model"] = getattr(response, "model", None)
            entry["response_text"] = extract_assistant_text(response) or ""
            entry["response"] = _response_payload(response)
        if error is not None:
            entry["error"] = {
                "type": error.__class__.__name__,
                "message": str(error),
            }
        safe_entry = _json_safe(entry)
        if isinstance(safe_entry, dict):
            _write_llm_log(safe_entry)

    def _invoke_with_logging(
        self,
        *,
        requested_provider: str,
        provider: str,
        requested_model: str,
        request: Dict[str, Any],
        route_reason: Optional[str],
        stream: bool,
        call: Any,
    ) -> Any:
        run_id = RUN_LOG_ID.get() or os.getenv("RUN_LOG_ID")
        entry = None
        if run_id:
            entry = register_request(
                run_id=run_id,
                provider=provider,
                model=requested_model,
                stream=stream,
                request=request,
            )
        request_id = entry.request_id if entry else None

        def _call_with_cancellation() -> Any:
            if not entry or stream:
                return call()
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(call)
                while True:
                    try:
                        return future.result(timeout=_LLM_CANCEL_POLL_SECONDS)
                    except concurrent.futures.TimeoutError:
                        if entry.cancel_event.is_set():
                            if future.done():
                                return future.result()
                            if entry.retry_event.is_set():
                                entry.cancel_event.clear()
                                entry.retry_event.clear()
                                entry.retry_count += 1
                                entry.last_retry_at = time.time()
                                return _LLM_RETRY_SENTINEL
                            raise LLMRequestCancelled(
                                f"LLM request cancelled for run_id={entry.run_id}"
                            )

        try:
            while True:
                start = time.time()
                try:
                    response = _call_with_cancellation()
                except Exception as exc:
                    duration_ms = (time.time() - start) * 1000.0
                    self._log_llm_call(
                        requested_provider=requested_provider,
                        provider=provider,
                        requested_model=requested_model,
                        request=request,
                        error=exc,
                        route_reason=route_reason,
                        duration_ms=duration_ms,
                        stream=stream,
                    )
                    raise
                if entry and not stream and entry.retry_event.is_set():
                    entry.cancel_event.clear()
                    entry.retry_event.clear()
                    entry.retry_count += 1
                    entry.last_retry_at = time.time()
                    logger.info(
                        "LLM manual retry requested (post-response) run_id=%s provider=%s model=%s",
                        run_id,
                        provider,
                        requested_model,
                    )
                    continue
                if response is _LLM_RETRY_SENTINEL:
                    logger.info(
                        "LLM manual retry requested run_id=%s provider=%s model=%s",
                        run_id,
                        provider,
                        requested_model,
                    )
                    continue
                duration_ms = (time.time() - start) * 1000.0
                self._log_llm_call(
                    requested_provider=requested_provider,
                    provider=provider,
                    requested_model=requested_model,
                    request=request,
                    response=response,
                    route_reason=route_reason,
                    duration_ms=duration_ms,
                    stream=stream,
                )
                return response
        finally:
            if run_id and request_id:
                clear_request(run_id, request_id)

    def _deepseek_unsupported(
        self,
        *,
        messages: Any,
        input: Any,
        conversation: Optional[str],
        previous_response_id: Optional[str],
        carry_items: Optional[List[InputItem]],
    ) -> List[str]:
        issues: List[str] = []
        if messages is not None and _messages_have_images(messages):
            issues.append("image_content")
        if input is not None and _input_has_images(input):
            issues.append("image_content")
        if conversation or previous_response_id or carry_items:
            issues.append("responses_api_features")
        return issues

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
        reasoning_effort: Optional[str] = None,
        reasoning_summary: Optional[str] = None,
        carry_items: Optional[List[InputItem]] = None,
        max_retries: Optional[int] = None,
        retry_backoff_base: Optional[float] = None,
        retry_backoff_cap: Optional[float] = None,
        retry_backoff_jitter: Optional[float] = None,
        stream: bool = False,
        **kwargs: Any,
    ) -> Any:
        resolved_model = _resolve_model(self._provider, model or self._default_model_raw)
        extra_kwargs = dict(kwargs) if kwargs else None

        def build_request_log(model_used: str) -> Dict[str, Any]:
            return _build_request_log(
                messages=messages,
                input=input,
                params={
                    "model": model_used,
                    "raw_model": model,
                    "max_output_tokens": max_output_tokens,
                    "tools": tools,
                    "conversation": conversation,
                    "previous_response_id": previous_response_id,
                    "reasoning_effort": reasoning_effort,
                    "reasoning_summary": reasoning_summary,
                    "carry_items": carry_items,
                    "max_retries": max_retries,
                    "retry_backoff_base": retry_backoff_base,
                    "retry_backoff_cap": retry_backoff_cap,
                    "retry_backoff_jitter": retry_backoff_jitter,
                    "stream": stream,
                },
                extra=extra_kwargs,
            )

        if self._provider == "deepseek":
            issues = self._deepseek_unsupported(
                messages=messages,
                input=input,
                conversation=conversation,
                previous_response_id=previous_response_id,
                carry_items=carry_items,
            )
            if issues:
                issue_set = set(issues)
                if issue_set == {"image_content"}:
                    image_client = self._get_image_client()
                    if image_client is not None:
                        image_model = _resolve_model(
                            self._image_provider or "openrouter",
                            model or self._default_model_raw,
                        )
                        logger.warning(
                            "DeepSeek image content; routing to %s.",
                            self._image_provider,
                        )
                        return self._invoke_with_logging(
                            requested_provider=self._provider,
                            provider=self._image_provider or "openrouter",
                            requested_model=image_model,
                            request=build_request_log(image_model),
                            route_reason="image_content",
                            stream=stream,
                            call=lambda: image_client.create_response(
                                model=image_model,
                                messages=messages,
                                input=input,
                                max_output_tokens=max_output_tokens,
                                tools=tools,
                                conversation=conversation,
                                previous_response_id=previous_response_id,
                                reasoning_effort=reasoning_effort,
                                reasoning_summary=reasoning_summary,
                                carry_items=carry_items,
                                max_retries=max_retries,
                                retry_backoff_base=retry_backoff_base,
                                retry_backoff_cap=retry_backoff_cap,
                                retry_backoff_jitter=retry_backoff_jitter,
                                stream=stream,
                                **kwargs,
                            ),
                        )

                fallback = self._get_fallback_client()
                if fallback is None:
                    raise ValueError(
                        "DeepSeek cannot handle: "
                        + ", ".join(sorted(issue_set))
                        + ". Set LLM_FALLBACK_PROVIDER=openai (or LLM_IMAGE_PROVIDER=openrouter for images)."
                    )
                logger.warning(
                    "DeepSeek unsupported features %s; falling back to %s.",
                    ",".join(sorted(issue_set)),
                    self._fallback_provider,
                )
                fallback_model = _resolve_model(
                    self._fallback_provider or "openai",
                    model or self._default_model_raw,
                )
                return self._invoke_with_logging(
                    requested_provider=self._provider,
                    provider=self._fallback_provider or "openai",
                    requested_model=fallback_model,
                    request=build_request_log(fallback_model),
                    route_reason="deepseek_unsupported:" + ",".join(sorted(issue_set)),
                    stream=stream,
                    call=lambda: fallback.create_response(
                        model=fallback_model,
                        messages=messages,
                        input=input,
                        max_output_tokens=max_output_tokens,
                        tools=tools,
                        conversation=conversation,
                        previous_response_id=previous_response_id,
                        reasoning_effort=reasoning_effort,
                        reasoning_summary=reasoning_summary,
                        carry_items=carry_items,
                        max_retries=max_retries,
                        retry_backoff_base=retry_backoff_base,
                        retry_backoff_cap=retry_backoff_cap,
                        retry_backoff_jitter=retry_backoff_jitter,
                        stream=stream,
                        **kwargs,
                    ),
                )

        return self._invoke_with_logging(
            requested_provider=self._provider,
            provider=self._provider,
            requested_model=resolved_model,
            request=build_request_log(resolved_model),
            route_reason=None,
            stream=stream,
            call=lambda: self._client.create_response(
                model=resolved_model,
                messages=messages,
                input=input,
                max_output_tokens=max_output_tokens,
                tools=tools,
                conversation=conversation,
                previous_response_id=previous_response_id,
                reasoning_effort=reasoning_effort,
                reasoning_summary=reasoning_summary,
                carry_items=carry_items,
                max_retries=max_retries,
                retry_backoff_base=retry_backoff_base,
                retry_backoff_cap=retry_backoff_cap,
                retry_backoff_jitter=retry_backoff_jitter,
                stream=stream,
                **kwargs,
            ),
        )

    def stream_response(
        self,
        *,
        event_handler: Optional[Any] = None,
        **kwargs: Any,
    ) -> Any:
        def build_request_log(model_used: str) -> Dict[str, Any]:
            extra_kwargs = dict(kwargs)
            for key in (
                "messages",
                "input",
                "model",
                "max_output_tokens",
                "tools",
                "conversation",
                "previous_response_id",
                "reasoning_effort",
                "reasoning_summary",
                "carry_items",
                "max_retries",
                "retry_backoff_base",
                "retry_backoff_cap",
                "retry_backoff_jitter",
                "stream",
            ):
                extra_kwargs.pop(key, None)
            return _build_request_log(
                messages=kwargs.get("messages"),
                input=kwargs.get("input"),
                params={
                    "model": model_used,
                    "raw_model": kwargs.get("model"),
                    "max_output_tokens": kwargs.get("max_output_tokens"),
                    "tools": kwargs.get("tools"),
                    "conversation": kwargs.get("conversation"),
                    "previous_response_id": kwargs.get("previous_response_id"),
                    "reasoning_effort": kwargs.get("reasoning_effort"),
                    "reasoning_summary": kwargs.get("reasoning_summary"),
                    "carry_items": kwargs.get("carry_items"),
                    "max_retries": kwargs.get("max_retries"),
                    "retry_backoff_base": kwargs.get("retry_backoff_base"),
                    "retry_backoff_cap": kwargs.get("retry_backoff_cap"),
                    "retry_backoff_jitter": kwargs.get("retry_backoff_jitter"),
                    "stream": True,
                },
                extra=extra_kwargs if extra_kwargs else None,
            )
        if self._provider == "deepseek":
            issues = self._deepseek_unsupported(
                messages=kwargs.get("messages"),
                input=kwargs.get("input"),
                conversation=kwargs.get("conversation"),
                previous_response_id=kwargs.get("previous_response_id"),
                carry_items=kwargs.get("carry_items"),
            )
            if issues:
                issue_set = set(issues)
                if issue_set == {"image_content"}:
                    image_client = self._get_image_client()
                    if image_client is not None:
                        kwargs["model"] = _resolve_model(
                            self._image_provider or "openrouter",
                            kwargs.get("model") or self._default_model_raw,
                        )
                        logger.warning(
                            "DeepSeek image content; routing to %s.",
                            self._image_provider,
                        )
                        image_model = kwargs["model"]
                        return self._invoke_with_logging(
                            requested_provider=self._provider,
                            provider=self._image_provider or "openrouter",
                            requested_model=image_model,
                            request=build_request_log(image_model),
                            route_reason="image_content",
                            stream=True,
                            call=lambda: image_client.stream_response(
                                event_handler=event_handler, **kwargs
                            ),
                        )

                fallback = self._get_fallback_client()
                if fallback is None:
                    raise ValueError(
                        "DeepSeek cannot handle: "
                        + ", ".join(sorted(issue_set))
                        + ". Set LLM_FALLBACK_PROVIDER=openai (or LLM_IMAGE_PROVIDER=openrouter for images)."
                    )
                logger.warning(
                    "DeepSeek unsupported features %s; falling back to %s.",
                    ",".join(sorted(issue_set)),
                    self._fallback_provider,
                )
                kwargs["model"] = _resolve_model(
                    self._fallback_provider or "openai",
                    kwargs.get("model") or self._default_model_raw,
                )
                fallback_model = kwargs["model"]
                return self._invoke_with_logging(
                    requested_provider=self._provider,
                    provider=self._fallback_provider or "openai",
                    requested_model=fallback_model,
                    request=build_request_log(fallback_model),
                    route_reason="deepseek_unsupported:" + ",".join(sorted(issue_set)),
                    stream=True,
                    call=lambda: fallback.stream_response(event_handler=event_handler, **kwargs),
                )
        kwargs["model"] = _resolve_model(
            self._provider, kwargs.get("model") or self._default_model_raw
        )
        default_model = kwargs["model"]
        return self._invoke_with_logging(
            requested_provider=self._provider,
            provider=self._provider,
            requested_model=default_model,
            request=build_request_log(default_model),
            route_reason=None,
            stream=True,
            call=lambda: self._client.stream_response(event_handler=event_handler, **kwargs),
        )


@lru_cache(maxsize=8)
def _get_client_singleton(
    *,
    provider: str,
    default_model: Optional[str],
    timeout: Optional[float],
    base_url: Optional[str],
) -> LLMClient:
    return LLMClient(
        provider=provider,
        default_model=default_model,
        timeout=timeout,
        base_url=base_url,
    )


def respond_once(
    *,
    messages: Optional[Iterable[Message]] = None,
    input: Optional[Union[InputItem, Sequence[InputItem], str]] = None,
    model: str = "o4-mini",
    max_output_tokens: Optional[int] = None,
    tools: Optional[List[Tool]] = None,
    reasoning_effort: str = "medium",
    reasoning_summary: Optional[str] = None,
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
    provider = _normalize_provider(None)
    client = _get_client_singleton(
        provider=provider,
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
) -> Any:
    provider = _normalize_provider(None)
    if timeout is None:
        timeout = get_default_llm_timeout()
    if provider == "deepseek":
        if _baseten_enabled_for_deepseek():
            from shared.baseten_client import get_client as get_baseten_client

            return get_baseten_client(api_key=api_key, timeout=timeout, base_url=base_url)
        from shared.deepseek_client import get_client as get_deepseek_client

        return get_deepseek_client(api_key=api_key, timeout=timeout, base_url=base_url)
    if provider == "openrouter":
        from shared.openrouter_client import get_client as get_openrouter_client

        return get_openrouter_client(api_key=api_key, timeout=timeout, base_url=base_url)
    from shared.oai_client import get_client as get_openai_client

    return get_openai_client(api_key=api_key, timeout=timeout, base_url=base_url)
