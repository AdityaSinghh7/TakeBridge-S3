"""Custom exceptions for the orchestrator agent."""

from __future__ import annotations


class HandbackRequested(Exception):
    """
    Raised when the computer-use agent requests human intervention.
    
    This exception propagates from the runner through the bridge to the
    orchestrator runtime, signaling that the run should pause and wait
    for human action before continuing.
    """

    def __init__(self, request: str, run_id: str):
        self.request = request
        self.run_id = run_id
        super().__init__(f"Handback requested: {request}")


__all__ = ["HandbackRequested"]

