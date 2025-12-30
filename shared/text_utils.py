"""Text normalization helpers for safe logging and output."""

from __future__ import annotations

from typing import Any


def _coerce_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="backslashreplace")
    return str(value)


def safe_ascii(value: Any) -> str:
    """Return ASCII-only text with non-ASCII escaped."""
    text = _coerce_text(value)
    return text.encode("ascii", errors="backslashreplace").decode("ascii")


def safe_utf8(value: Any) -> str:
    """Return UTF-8 text with a defensive error handler."""
    text = _coerce_text(value)
    return text.encode("utf-8", errors="backslashreplace").decode("utf-8")


__all__ = ["safe_ascii", "safe_utf8"]
