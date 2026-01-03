from __future__ import annotations

from typing import Any, Callable, Dict, Iterable, Optional

from shared.llm_client import LLMClient, extract_assistant_text
from shared.latency_logger import LATENCY_LOGGER
from shared.token_cost_tracker import TOKEN_TRACKER


class LMMEngine:
    """Base LMM engine placeholder for compatibility."""

    def generate(
        self,
        messages: Iterable[Dict[str, Any]],
        temperature: float = 0.0,
        max_new_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> str:
        raise NotImplementedError


class LMMEngineOpenAI(LMMEngine):
    """Thin wrapper around the LLM facade via `LLMClient`."""

    def __init__(
        self,
        *,
        model: str,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        temperature: Optional[float] = None,
        reasoning_effort: str = "medium",
        reasoning_summary: Optional[str] = None,
        timeout: Optional[float] = None,
        default_tools: Optional[list] = None,
        max_output_tokens: Optional[int] = None,
        max_retries: Optional[int] = None,
        retry_backoff_base: Optional[float] = None,
        retry_backoff_cap: Optional[float] = None,
        retry_backoff_jitter: Optional[float] = None,
        **_: Any,
    ) -> None:
        self.model = model
        self.temperature_override = temperature
        self.reasoning_effort = reasoning_effort
        self.reasoning_summary = reasoning_summary
        self.max_output_tokens = max_output_tokens
        self.default_tools = default_tools

        client_kwargs: Dict[str, Any] = {
            "api_key": api_key,
            "default_model": model,
            "default_reasoning_effort": reasoning_effort,
            "default_reasoning_summary": reasoning_summary,
            "timeout": timeout,
            "base_url": base_url,
            "default_tools": default_tools,
        }
        if max_retries is not None:
            client_kwargs["max_retries"] = max_retries
        if retry_backoff_base is not None:
            client_kwargs["retry_backoff_base"] = retry_backoff_base
        if retry_backoff_cap is not None:
            client_kwargs["retry_backoff_cap"] = retry_backoff_cap
        if retry_backoff_jitter is not None:
            client_kwargs["retry_backoff_jitter"] = retry_backoff_jitter

        self.client = LLMClient(**client_kwargs)
        self.model = self.client.default_model
        self._supports_temperature = not (
            isinstance(self.model, str) and self.model.lower().startswith("o4-")
        )

    def generate(
        self,
        messages: Iterable[Dict[str, Any]],
        temperature: float = 0.0,
        max_new_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> str:
        source_name = kwargs.pop("cost_source", "openai.generate")
        kwargs.pop("temperature", None)
        stream_handler: Optional[Callable[[Any], None]] = kwargs.pop("stream_handler", None)
        stream_enabled = bool(kwargs.pop("stream", False) or stream_handler)
        if stream_handler is not None and not callable(stream_handler):
            raise TypeError("stream_handler must be callable.")

        # Avoid forwarding duplicate token caps to the underlying client.
        explicit_max_tokens = kwargs.pop("max_output_tokens", None)

        temperature_to_use = (
            self.temperature_override
            if self.temperature_override is not None
            else temperature
        )
        reasoning_effort = kwargs.pop("reasoning_effort", self.reasoning_effort)
        reasoning_summary = kwargs.pop("reasoning_summary", self.reasoning_summary)
        tools = kwargs.pop("tools", None) or self.default_tools
        max_output_tokens = (
            max_new_tokens
            or explicit_max_tokens
            or self.max_output_tokens
        )

        message_list = list(messages)

        temperature_param = (
            temperature_to_use if self._supports_temperature else None
        )

        with LATENCY_LOGGER.measure(
            "openai", f"{source_name}.request", extra={"model": self.model}
        ):
            request_kwargs: Dict[str, Any] = {
                "model": self.model,
                "messages": message_list,
                "tools": tools,
                "max_output_tokens": max_output_tokens,
                "reasoning_effort": reasoning_effort,
                "reasoning_summary": reasoning_summary,
            }
            request_kwargs.update(kwargs)
            if temperature_param is not None:
                request_kwargs["temperature"] = temperature_param
            if stream_enabled:
                response = self.client.stream_response(
                    event_handler=stream_handler,
                    **request_kwargs,
                )
            else:
                response = self.client.create_response(**request_kwargs)

        model_name = getattr(response, "model", None) or self.model
        TOKEN_TRACKER.record_response(model_name, source_name, response)
        return extract_assistant_text(response) or ""
