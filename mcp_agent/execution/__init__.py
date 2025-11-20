"""Execution layer: I/O processing and sandbox runtime."""

from .envelope import normalize_action_response, process_observation
from .sandbox import run_python_plan, SandboxResult

__all__ = [
    "normalize_action_response",
    "process_observation",
    "run_python_plan",
    "SandboxResult",
]

