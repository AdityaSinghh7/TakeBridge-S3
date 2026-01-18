"""Token counting utility for JSON payloads using model-appropriate tokenizers."""

import json
import os
from functools import lru_cache
from typing import Any, Optional

try:
    import tiktoken
except Exception:  # pragma: no cover
    tiktoken = None  # type: ignore[assignment]

_HF_MODEL_ALIASES = {
    "deepseek-reasoner": "deepseek-ai/DeepSeek-V3.2",
    "deepseek-chat": "deepseek-ai/DeepSeek-V3.2",
    "qwen/qwen3-vl-235b-a22b-instruct": "Qwen/Qwen3-VL-235B-A22B-Instruct",
}


def _env_flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _normalize_provider(value: Optional[str]) -> str:
    raw = (value or os.getenv("LLM_PROVIDER", "openai")).strip().lower()
    if raw in {"oai", "openai", "open-ai"}:
        return "openai"
    if raw in {"deepseek", "deep-seek"}:
        return "deepseek"
    if raw in {"openrouter", "open-router", "open_router"}:
        return "openrouter"
    return "openai"


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


def _default_model_from_env() -> str:
    provider = _normalize_provider(None)
    if provider == "deepseek":
        if _env_flag("DEEPSEEK_BASETEN_ENABLED"):
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


def _resolve_model_name(model: Optional[str]) -> str:
    if model and str(model).strip():
        return str(model).strip()
    return _default_model_from_env()


def _tokenizer_model_id(model_name: str) -> str:
    override = os.getenv("TOKENIZER_MODEL") or os.getenv("TOKENIZER_MODEL_ID")
    if override:
        return str(override).strip()
    lower = model_name.strip().lower()
    return _HF_MODEL_ALIASES.get(lower, model_name)


def _preferred_backend(model_name: str) -> str:
    forced = os.getenv("TOKENIZER_BACKEND", "").strip().lower()
    if forced in {"hf", "transformers"}:
        return "hf"
    if forced == "tiktoken":
        return "tiktoken"
    lower = model_name.lower()
    if "deepseek" in lower or "qwen" in lower:
        return "hf"
    return "tiktoken"


@lru_cache(maxsize=4)
def _get_hf_tokenizer(model_id: str):
    try:
        from transformers import AutoTokenizer
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("transformers not available") from exc

    local_only = not _env_flag("TOKENIZER_ALLOW_REMOTE")
    return AutoTokenizer.from_pretrained(
        model_id,
        use_fast=True,
        trust_remote_code=True,
        local_files_only=local_only,
    )


def _count_tokens_hf(text: str, model_name: str) -> Optional[int]:
    model_id = _tokenizer_model_id(model_name)
    try:
        tokenizer = _get_hf_tokenizer(model_id)
    except Exception:
        return None
    try:
        return len(tokenizer.encode(text, add_special_tokens=False))
    except Exception:
        return None


def _count_tokens_tiktoken(text: str, model_name: str) -> Optional[int]:
    if tiktoken is None:
        return None
    try:
        encoding = tiktoken.encoding_for_model(model_name)
    except Exception:
        try:
            encoding = tiktoken.get_encoding("cl100k_base")
        except Exception:
            return None
    try:
        return len(encoding.encode(text))
    except Exception:
        return None


def count_json_tokens(data: Any, model: Optional[str] = None) -> int:
    """
    Count tokens in a JSON-serializable payload.

    Uses model-appropriate tokenizers when available:
    - OpenAI-style models: tiktoken encoding_for_model
    - DeepSeek/Qwen models: transformers AutoTokenizer if cached locally

    Args:
        data: Any JSON-serializable Python object (dict, list, str, etc.)
        model: Optional model name for encoding selection (defaults to env-derived model)

    Returns:
        Token count as integer

    Raises:
        ValueError: If data is not JSON-serializable

    Examples:
        >>> count_json_tokens({"key": "value"})
        7
        >>> count_json_tokens([1, 2, 3, 4, 5])
        11
    """
    model_name = _resolve_model_name(model)

    # Serialize to JSON string
    try:
        json_str = json.dumps(data, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        json_str = str(data)

    backend = _preferred_backend(model_name)
    token_count: Optional[int] = None
    if backend == "hf":
        token_count = _count_tokens_hf(json_str, model_name)
        if token_count is None:
            token_count = _count_tokens_tiktoken(json_str, model_name)
    else:
        token_count = _count_tokens_tiktoken(json_str, model_name)
        if token_count is None:
            token_count = _count_tokens_hf(json_str, model_name)

    if token_count is not None:
        return token_count

    # If tokenizers are unavailable, estimate based on string length.
    return len(json_str) // 3
