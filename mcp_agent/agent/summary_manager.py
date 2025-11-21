"""Output summarization and storage management.

Manages summarization of tool and sandbox outputs, including:
- Deciding when outputs need summarization
- Managing storage paths for large outputs
- Recording summarization events
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Callable, Dict, Optional


def _summarize_for_storage(
    label: str,
    payload: Any,
    *,
    purpose: str = "storage",
    storage_dir: Path | None = None,
    persist_payload: bool = False,
) -> Dict[str, Any]:
    """Simple storage summarization (inline version)."""
    try:
        serialized = json.dumps(payload, default=str, ensure_ascii=False)
        if len(serialized) > 50000:
            return {
                "truncated": True,
                "size": len(serialized),
                "label": label,
            }
        return {}
    except Exception:
        return {}


class SummaryManager:
    """Manages output summarization and storage.

    Responsibilities:
    - Decide when outputs need summarization (size/count thresholds)
    - Coordinate summarization and storage
    - Record summarization events
    - Manage storage paths

    NOT responsible for:
    - Executing tools (see executor.py)
    - Formatting summaries for LLM (see history.py)
    - Making decisions (see orchestrator.py)
    """

    def __init__(
        self,
        task_id: str,
        event_recorder: Callable[[str, Dict[str, Any]], None],
        summary_threshold_bytes: int = 16_000,
        summary_item_limit: int = 50,
    ) -> None:
        """Initialize summary manager.

        Args:
            task_id: Task identifier for storage paths
            event_recorder: Callback for recording events
            summary_threshold_bytes: Size threshold for summarization
            summary_item_limit: Item count threshold for summarization
        """
        self._task_id = task_id
        self._record_event = event_recorder
        self._summary_threshold_bytes = summary_threshold_bytes
        self._summary_item_limit = summary_item_limit
        self._summary_root = self._init_summary_root(task_id)
        self._persist_summaries = os.getenv("MCP_SUMMARY_ALWAYS_PERSIST", "").lower() in {
            "1",
            "true",
            "yes",
            "on",
        }

    @property
    def summary_root(self) -> Path:
        """Get the root directory for summary storage."""
        return self._summary_root

    def summarize_tool_output(
        self,
        label: str,
        payload: Any,
        *,
        purpose: str = "for_planning",
        force: bool = False,
    ) -> Dict[str, Any]:
        """Summarize tool output for logging/storage purposes.

        Args:
            label: Label for the output (e.g., "gmail.fetch_emails")
            payload: The output payload to potentially summarize
            purpose: Purpose string for logging
            force: Force summarization regardless of size

        Returns:
            Summary dict with metadata (empty if no summarization needed)
        """
        return self._summarize_and_record(
            label,
            payload,
            purpose=purpose,
            storage_subdir="tools",
            force=force,
        )

    def summarize_sandbox_output(
        self,
        label: str,
        payload: Any,
        *,
        purpose: str = "for_planning",
        force: bool = False,
    ) -> Dict[str, Any]:
        """Summarize sandbox output for logging/storage purposes.

        Args:
            label: Label for the output (e.g., "sandbox.run")
            payload: The output payload to potentially summarize
            purpose: Purpose string for logging
            force: Force summarization regardless of size

        Returns:
            Summary dict with metadata (empty if no summarization needed)
        """
        return self._summarize_and_record(
            label,
            payload,
            purpose=purpose,
            storage_subdir="sandbox",
            force=force,
        )

    def should_summarize(self, payload: Any) -> bool:
        """Check if payload needs summarization based on size/count thresholds.

        Args:
            payload: The payload to check

        Returns:
            True if summarization is needed
        """
        size = self._estimate_bytes(payload)
        if size > self._summary_threshold_bytes:
            return True

        if isinstance(payload, (list, tuple)) and len(payload) > self._summary_item_limit:
            return True

        if isinstance(payload, dict) and len(payload) > self._summary_item_limit:
            return True

        return False

    def _summarize_and_record(
        self,
        label: str,
        payload: Any,
        *,
        purpose: str,
        storage_subdir: str,
        force: bool = False,
    ) -> Dict[str, Any]:
        """Summarize payload and record the event.

        Args:
            label: Label for the output
            payload: The output payload
            purpose: Purpose string for logging
            storage_subdir: Subdirectory for storage (tools/sandbox)
            force: Force summarization regardless of size

        Returns:
            Summary dict with metadata
        """
        if not force and not self.should_summarize(payload):
            return {}

        storage_dir = self._summary_root / storage_subdir
        summary = _summarize_for_storage(
            label,
            payload,
            purpose=purpose,
            storage_dir=storage_dir,
            persist_payload=self._persist_summaries,
        )

        # Record events for telemetry
        self._record_event(
            "mcp.summary.created",
            {
                "label": label,
                "purpose": purpose,
                "truncated": summary.get("truncated"),
            },
        )

        if summary.get("storage_ref"):
            self._record_event(
                "mcp.redaction.applied",
                {
                    "label": label,
                    "purpose": purpose,
                    "storage_ref": summary["storage_ref"],
                },
            )

        return summary

    def _estimate_bytes(self, payload: Any) -> int:
        """Estimate byte size of payload."""
        try:
            serialized = json.dumps(payload, ensure_ascii=False, default=str)
        except TypeError:
            serialized = str(payload)
        return len(serialized.encode("utf-8"))

    @staticmethod
    def _init_summary_root(task_id: str) -> Path:
        """Initialize summary storage root directory.

        Tries multiple locations in order of preference:
        1. /workspace/tool-results/{task_id}
        2. logs/tool-results/{task_id}

        Args:
            task_id: Task identifier for storage path

        Returns:
            Path to summary root directory
        """
        candidates = [
            Path("/workspace/tool-results") / task_id,
            Path("logs") / "tool-results" / task_id,
        ]

        for root in candidates:
            try:
                root.mkdir(parents=True, exist_ok=True)
                return root
            except OSError:
                continue

        # Fallback
        fallback = Path("logs") / "tool-results" / task_id
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback
