"""
Logging helpers shared across agents.

Provides a thin wrapper around the standard logging module to simplify
consistent line-by-line output across the codebase.
"""

from __future__ import annotations

import logging
from typing import Iterable, Union


class StructuredLogger:
    """Convenience wrapper enabling structured line-by-line logging."""

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
        """Emit a header (optional) followed by each line as INFO logs."""
        if header:
            self.info(header)
        for line in lines:
            self.info(f"{prefix}{line}")


__all__ = ["StructuredLogger"]

