from __future__ import annotations

import os


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        return float(raw)
    except Exception:
        return default


DEFAULT_LLM_TIMEOUT_SECONDS = _env_float("LLM_TIMEOUT_SECONDS", 600.0)


def get_default_llm_timeout() -> float:
    return DEFAULT_LLM_TIMEOUT_SECONDS

