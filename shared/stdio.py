"""Standard stream configuration helpers."""

from __future__ import annotations

import logging
import sys
from typing import Iterable

logger = logging.getLogger(__name__)


def ensure_utf8_stdio(stream_names: Iterable[str] = ("stdout", "stderr")) -> None:
    """Best-effort reconfigure standard streams for UTF-8 output."""
    for name in stream_names:
        stream = getattr(sys, name, None)
        if stream is None:
            continue
        reconfigure = getattr(stream, "reconfigure", None)
        if not callable(reconfigure):
            continue
        try:
            reconfigure(encoding="utf-8", errors="backslashreplace")
        except Exception as exc:
            logger.debug("Failed to reconfigure %s: %s", name, exc)


__all__ = ["ensure_utf8_stdio"]
