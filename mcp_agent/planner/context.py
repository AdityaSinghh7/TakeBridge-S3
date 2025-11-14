from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from shared.streaming import emit_event
from shared.token_cost_tracker import TokenCostTracker

from .summarize import redact_payload, summarize_payload

from .budget import Budget, BudgetTracker
from .prompt import PLANNER_PROMPT


@dataclass
class PlannerContext:
    """State container for a single planner run."""

    task: str
    user_id: str
    budget: Budget
    toolbox_root: Path = field(default_factory=lambda: Path("toolbox"))
    task_id: Optional[str] = None
    planner_prompt: str = PLANNER_PROMPT
    extra_context: Dict[str, Any] = field(default_factory=dict)
    search_results: List[Dict[str, Any]] = field(default_factory=list)
    tool_menu: List[Dict[str, Any]] = field(default_factory=list)
    tool_summaries: List[Dict[str, Any]] = field(default_factory=list)
    sandbox_summaries: List[Dict[str, Any]] = field(default_factory=list)
    logs: List[Dict[str, Any]] = field(default_factory=list)
    token_tracker: TokenCostTracker = field(default_factory=TokenCostTracker)
    discovery_completed: bool = False
    raw_outputs: Dict[str, Any] = field(default_factory=dict)
    registry_version: Optional[int] = None

    def __post_init__(self) -> None:
        self.budget_tracker = BudgetTracker(self.budget)
        self.toolbox_root = Path(self.toolbox_root).resolve()
        if not self.task_id:
            self.task_id = self._generate_task_id()
        self.summary_root = self._init_summary_root()
        self.summary_threshold_bytes = 16_000
        self.summary_item_limit = 50
        self._search_index: Dict[str, Dict[str, Any]] = {}

    def record_event(self, event: str, payload: Dict[str, Any]) -> None:
        safe_payload = self._redact_for_logs(payload)
        enriched = {"task": self.task, "task_id": self.task_id, "user_id": self.user_id, **safe_payload}
        log_entry = {"event": event, **enriched}
        self.logs.append(log_entry)
        emit_event(event, enriched)

    def add_search_results(self, results: List[Dict[str, Any]], *, replace: bool = False) -> None:
        if replace:
            self.search_results.clear()
            self._search_index.clear()
        for entry in results:
            key = self._search_key(entry)
            if not key:
                continue
            existing = self._search_index.get(key)
            if existing:
                if self._score(entry) > self._score(existing):
                    idx = self._find_search_index(key)
                    if idx is not None:
                        self.search_results[idx] = entry
                        self._search_index[key] = entry
                continue
            self.search_results.append(entry)
            self._search_index[key] = entry
        self._trim_context()
        self._update_tool_menu()
        self.discovery_completed = True

    def replace_search_results(self, results: List[Dict[str, Any]]) -> None:
        self.add_search_results(results, replace=True)

    def add_tool_summary(self, summary: Dict[str, Any]) -> None:
        self.tool_summaries.append(summary)
        self._trim_context()

    def add_sandbox_summary(self, summary: Dict[str, Any]) -> None:
        self.sandbox_summaries.append(summary)
        self._trim_context()

    def summarize_tool_output(
        self,
        label: str,
        payload: Any,
        *,
        purpose: str = "for_planning",
        force: bool = False,
    ) -> Dict[str, Any]:
        if not force and not self.should_summarize(payload):
            return {}
        storage_dir = self.summary_root / "tools"
        summary = summarize_payload(
            label,
            payload,
            purpose=purpose,
            storage_dir=storage_dir,
            persist_payload=True,
        )
        self.add_tool_summary(summary)
        self.record_event(
            "mcp.summary.created",
            {
                "label": label,
                "purpose": purpose,
                "truncated": summary.get("truncated"),
            },
        )
        if summary.get("storage_ref"):
            self.record_event(
                "mcp.redaction.applied",
                {
                    "label": label,
                    "purpose": purpose,
                    "storage_ref": summary["storage_ref"],
                },
            )
        return summary

    def summarize_sandbox_output(
        self,
        label: str,
        payload: Any,
        *,
        purpose: str = "for_planning",
        force: bool = False,
    ) -> Dict[str, Any]:
        if not force and not self.should_summarize(payload):
            return {}
        storage_dir = self.summary_root / "sandbox"
        summary = summarize_payload(
            label,
            payload,
            purpose=purpose,
            storage_dir=storage_dir,
            persist_payload=True,
        )
        self.add_sandbox_summary(summary)
        self.record_event(
            "mcp.summary.created",
            {
                "label": label,
                "purpose": purpose,
                "truncated": summary.get("truncated"),
            },
        )
        if summary.get("storage_ref"):
            self.record_event(
                "mcp.redaction.applied",
                {
                    "label": label,
                    "purpose": purpose,
                    "storage_ref": summary["storage_ref"],
                },
            )
        return summary

    def should_summarize(self, payload: Any) -> bool:
        size = self._estimate_bytes(payload)
        if size > self.summary_threshold_bytes:
            return True
        if isinstance(payload, (list, tuple)) and len(payload) > self.summary_item_limit:
            return True
        if isinstance(payload, dict) and len(payload) > self.summary_item_limit:
            return True
        return False

    def _estimate_bytes(self, payload: Any) -> int:
        try:
            serialized = json.dumps(payload, ensure_ascii=False, default=str)
        except TypeError:
            serialized = str(payload)
        return len(serialized.encode("utf-8"))

    def _trim_context(self, max_items: int = 50) -> None:
        """Keep only the most recent summaries to enforce deterministic caps."""
        if len(self.tool_summaries) > max_items:
            self.tool_summaries[:] = self.tool_summaries[-max_items:]
        if len(self.sandbox_summaries) > max_items:
            self.sandbox_summaries[:] = self.sandbox_summaries[-max_items:]
        if len(self.search_results) > max_items:
            self.search_results[:] = self.search_results[-max_items:]
            self._search_index = {self._search_key(entry): entry for entry in self.search_results if self._search_key(entry)}
        self._update_tool_menu()

    def _redact_for_logs(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        try:
            return redact_payload(payload)
        except Exception:
            return payload

    def _generate_task_id(self) -> str:
        digest = hashlib.sha1(f"{self.user_id}:{self.task}".encode("utf-8")).hexdigest()[:10]
        base = re.sub(r"[^a-zA-Z0-9_-]", "-", self.user_id).strip("-") or "task"
        return f"{base}-{digest}"

    def _init_summary_root(self) -> Path:
        candidates = [
            Path("/workspace/tool-results") / (self.task_id or "task"),
            Path("logs") / "tool-results" / (self.task_id or "task"),
        ]
        for root in candidates:
            try:
                root.mkdir(parents=True, exist_ok=True)
                return root
            except OSError:
                continue
        fallback = Path("logs") / "tool-results" / (self.task_id or "task")
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback

    def _search_key(self, entry: Dict[str, Any]) -> Optional[str]:
        provider = (entry.get("provider") or "").strip().lower()
        tool = (entry.get("tool") or "").strip().lower()
        if not provider or not tool:
            return None
        return f"{provider}.{tool}"

    def _find_search_index(self, key: str) -> Optional[int]:
        for idx, entry in enumerate(self.search_results):
            if self._search_key(entry) == key:
                return idx
        return None

    def _score(self, entry: Dict[str, Any]) -> float:
        value = entry.get("score")
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    def _update_tool_menu(self, limit: int = 8) -> None:
        top_items = self.search_results[:limit]
        menu = []
        for entry in top_items:
            key = self._search_key(entry)
            if not key:
                continue
            menu.append(
                {
                    "qualified_name": key,
                    "provider": entry.get("provider"),
                    "tool": entry.get("tool"),
                    "available": entry.get("available"),
                    "short_description": entry.get("short_description") or entry.get("description") or "",
                    "parameters": entry.get("parameters", []),
                }
            )
        self.tool_menu = menu
