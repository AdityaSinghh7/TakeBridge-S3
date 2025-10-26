from __future__ import annotations

from typing import Any, Dict, Iterable, Optional

from framework.api.oai_client import OAIClient, extract_assistant_text


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
    """Thin wrapper around the OpenAI Responses API via `OAIClient`."""

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

        self.client = OAIClient(**client_kwargs)

    def generate(
        self,
        messages: Iterable[Dict[str, Any]],
        temperature: float = 0.0,
        max_new_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> str:
        temperature_to_use = (
            self.temperature_override
            if self.temperature_override is not None
            else temperature
        )
        reasoning_effort = kwargs.pop("reasoning_effort", self.reasoning_effort)
        reasoning_summary = kwargs.pop("reasoning_summary", self.reasoning_summary)
        tools = kwargs.pop("tools", None) or self.default_tools
        max_output_tokens = max_new_tokens or self.max_output_tokens

        response = self.client.create_response(
            model=self.model,
            messages=list(messages),
            tools=tools,
            max_output_tokens=max_output_tokens,
            reasoning_effort=reasoning_effort,
            reasoning_summary=reasoning_summary,
            temperature=temperature_to_use,
            **kwargs,
        )
        return extract_assistant_text(response) or ""

