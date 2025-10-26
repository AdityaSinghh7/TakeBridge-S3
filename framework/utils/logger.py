"""
Logging helpers for the TakeBridge framework.

Provides a thin wrapper around the standard logging module to simplify
consistent line-by-line output across the codebase.
"""

from __future__ import annotations

import logging
from typing import Iterable, Union


class StructuredLogger:
    """
    Convenience wrapper enabling structured line-by-line logging.

    Usage:
        logger = StructuredLogger(__name__)
        logger.info_lines("Header", ["line 1", "line 2"])
    """

    def __init__(self, name: str) -> None:
        self._logger = logging.getLogger(name)

    def info(self, message: str) -> None:
        self._logger.info(message)

    def info_lines(
        self,
        header: Union[str, None],
        lines: Iterable[str],
        *,
        prefix: str = "  ",
    ) -> None:
        """
        Emit a header (optional) followed by each line as an INFO log.
        """
        if header:
            self.info(header)
        for line in lines:
            self.info(f"{prefix}{line}")


__all__ = ["StructuredLogger"]
