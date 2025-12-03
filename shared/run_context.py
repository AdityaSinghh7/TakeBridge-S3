from __future__ import annotations

import contextvars
from typing import Optional

# Shared context for tagging log records with the current orchestrate run id.
RUN_LOG_ID: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "orchestrate_run_log_id",
    default=None,
)

__all__ = ["RUN_LOG_ID"]
