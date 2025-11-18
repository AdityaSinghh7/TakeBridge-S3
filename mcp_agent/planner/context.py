from __future__ import annotations

import hashlib
import json
import os
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Literal, Optional
import uuid

from shared.streaming import emit_event
from shared.token_cost_tracker import TokenCostTracker

from mcp_agent.toolbox.builder import get_index

from .summarize import redact_payload, summarize_payload

from .budget import Budget, BudgetSnapshot, BudgetTracker
from .prompt import PLANNER_PROMPT

StepType = Literal["tool", "sandbox", "search", "finish"]


@dataclass
class PlannerStep:
    index: int
    type: StepType
    command: Dict[str, Any]
    success: bool
    preview: str
    result_key: Optional[str] = None
    error: Optional[str] = None
    output: Any | None = None
    is_summary: bool = False


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
    steps: List[PlannerStep] = field(default_factory=list)
    run_id: str = field(default_factory=lambda: uuid.uuid4().hex)

    def __post_init__(self) -> None:
        self.budget_tracker = BudgetTracker(self.budget)
        self.toolbox_root = Path(self.toolbox_root).resolve()
        if not self.task_id:
            self.task_id = self._generate_task_id()
        self.summary_root = self._init_summary_root()
        self.summary_threshold_bytes = 16_000
        self.summary_item_limit = 50
        self._search_index: Dict[str, Dict[str, Any]] = {}
        self._persist_summaries = os.getenv("MCP_SUMMARY_ALWAYS_PERSIST", "").lower() in {
            "1",
            "true",
            "yes",
            "on",
        }

    # --- Logging & step history ---

    def record_event(self, event: str, payload: Dict[str, Any]) -> None:
        safe_payload = self.redact_for_logs(payload)
        enriched = {
            "task": self.task,
            "task_id": self.task_id,
            "user_id": self.user_id,
            "run_id": self.run_id,
            **safe_payload,
        }
        log_entry = {"event": event, **enriched}
        self.logs.append(log_entry)
        emit_event(event, enriched)

    def record_step(
        self,
        *,
        type: StepType,
        command: Dict[str, Any],
        success: bool,
        preview: str,
        result_key: str | None = None,
        error: str | None = None,
        output: Any | None = None,
        is_summary: bool = False,
    ) -> None:
        normalized_preview = preview.strip() or "n/a"
        self.steps.append(
            PlannerStep(
                index=len(self.steps),
                type=type,
                command=command,
                success=success,
                preview=normalized_preview[:200],
                result_key=result_key,
                error=error,
                output=output,
                is_summary=is_summary,
            )
        )

    # --- Search / discovery state ---

    def merge_search_results(self, results: List[Dict[str, Any]], *, replace: bool = False) -> None:
        """
        Merge new search results into the existing index, optionally replacing it.

        Deduplicates by provider+tool key and keeps the highest-scoring entry
        when duplicates are encountered.
        """
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
        self._trim_context_for_llm()
        self._update_tool_menu()
        self.discovery_completed = True

    def add_search_results(self, results: List[Dict[str, Any]], *, replace: bool = False) -> None:
        """
        Backwards-compatible alias for merge_search_results.

        Prefer merge_search_results(...) in new code.
        """
        self.merge_search_results(results, replace=replace)

    def set_search_results(self, results: List[Dict[str, Any]]) -> None:
        """Replace the current search results with the provided list."""
        self.merge_search_results(results, replace=True)

    def replace_search_results(self, results: List[Dict[str, Any]]) -> None:
        """Deprecated alias for set_search_results; preserved for compatibility."""
        self.set_search_results(results)

    # --- Summarization & raw outputs ---

    def add_tool_summary(self, summary: Dict[str, Any]) -> None:
        self.tool_summaries.append(summary)
        self._trim_context_for_llm()

    def add_sandbox_summary(self, summary: Dict[str, Any]) -> None:
        self.sandbox_summaries.append(summary)
        self._trim_context_for_llm()

    def resolve_mcp_tool_name(self, provider: str, tool_name: str) -> str:
        """
        Resolve a planner-facing provider/tool pair to the underlying MCP tool name.

        This uses the ToolboxIndex rather than exposing internal fields like
        `mcp_tool_name` in search results sent to the LLM.
        """
        provider_key = (provider or "").strip().lower()
        tool_key = (tool_name or "").strip()
        if not provider_key or not tool_key:
            return tool_name

        tool_id = f"{provider_key}.{tool_key}"
        try:
            index = get_index(self.user_id)
        except Exception:
            return tool_name
        spec = index.get_tool(tool_id)
        if spec and spec.mcp_tool_name:
            return spec.mcp_tool_name
        return tool_name

    def append_raw_output(self, key: str, entry: Dict[str, Any]) -> Dict[str, Any]:
        """Append a structured entry to `raw_outputs`, preserving older history."""
        existing = self.raw_outputs.get(key)
        if existing is None:
            self.raw_outputs[key] = [entry]
        elif isinstance(existing, list):
            existing.append(entry)
        else:
            self.raw_outputs[key] = [existing, entry]
        return entry

    def get_raw_output_entries(self, key: str) -> List[Dict[str, Any]]:
        value = self.raw_outputs.get(key)
        if value is None:
            return []
        if isinstance(value, list):
            return value
        return [value]

    def summarize_tool_output(
        self,
        label: str,
        payload: Any,
        *,
        purpose: str = "for_planning",
        force: bool = False,
    ) -> Dict[str, Any]:
        return self._summarize_and_record(
            label,
            payload,
            purpose=purpose,
            storage_subdir="tools",
            add_summary_fn=self.add_tool_summary,
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
        return self._summarize_and_record(
            label,
            payload,
            purpose=purpose,
            storage_subdir="sandbox",
            add_summary_fn=self.add_sandbox_summary,
            force=force,
        )

    def should_summarize(self, payload: Any) -> bool:
        size = self._estimate_bytes(payload)
        if size > self.summary_threshold_bytes:
            return True
        if isinstance(payload, (list, tuple)) and len(payload) > self.summary_item_limit:
            return True
        if isinstance(payload, dict) and len(payload) > self.summary_item_limit:
            return True
        return False

    def _summarize_and_record(
        self,
        label: str,
        payload: Any,
        *,
        purpose: str,
        storage_subdir: str,
        add_summary_fn: Callable[[Dict[str, Any]], None],
        force: bool = False,
    ) -> Dict[str, Any]:
        """Common helper to summarize a payload and record redaction telemetry."""
        if not force and not self.should_summarize(payload):
            return {}
        storage_dir = self.summary_root / storage_subdir
        summary = summarize_payload(
            label,
            payload,
            purpose=purpose,
            storage_dir=storage_dir,
            persist_payload=self._persist_summaries,
        )
        add_summary_fn(summary)
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

    def build_planner_state(self, _snapshot: BudgetSnapshot) -> Dict[str, Any]:
        """
        Build the planner_state JSON consumed by PlannerLLM; no side effects.
        """
        recent_count = 3
        recent_steps = self.steps[-recent_count:]
        history_summary = self._history_summary(len(recent_steps))
        tools_root = str((self.toolbox_root / "sandbox_py" / "servers").resolve())
        available_servers = sorted(
            {
                (entry.get("server") or entry.get("provider", "")).strip()
                for entry in self.search_results
                if (entry.get("server") or entry.get("provider"))
            }
        )
        recent_entries: List[Dict[str, Any]] = []
        for step in recent_steps:
            entry: Dict[str, Any] = {
                "index": step.index,
                "type": step.type,
                "status": "success" if step.success else "error",
                "summary": step.preview,
            }
            command = step.command or {}
            if step.type == "search":
                entry["query"] = command.get("query")
                entry["detail_level"] = command.get("detail_level")
                if isinstance(step.output, list):
                    entry["result_count"] = len(step.output)
            elif step.type == "sandbox":
                entry["label"] = command.get("label") or step.result_key
            elif step.type == "tool":
                entry["provider"] = command.get("provider")
                entry["tool"] = command.get("tool")
            if step.result_key:
                entry["result_key"] = step.result_key
            if step.error:
                entry["error"] = step.error
            if step.output is not None:
                entry["output"] = step.output
                entry["is_summary"] = step.is_summary
            recent_entries.append(entry)
        return {
            "task": self.task,
            "user_id": self.user_id,
            "run_id": self.run_id,
            "tools_root": tools_root,
            "available_servers": available_servers,
            "history_summary": history_summary,
            "recent_steps": recent_entries,
            # Full, de-duplicated catalog of tools discovered via search so far.
            "search_results": list(self.search_results),
        }

    def planner_state(self, snapshot: BudgetSnapshot) -> Dict[str, Any]:
        """
        Deprecated alias for build_planner_state; prefer build_planner_state().
        """
        return self.build_planner_state(snapshot)

    def _history_summary(self, recent_count: int) -> str:
        total = len(self.steps)
        earlier = total - recent_count
        if earlier <= 0:
            return "No earlier steps."
        counts = Counter(step.type for step in self.steps[:earlier])
        parts = [f"{counts[step_type]} {step_type}" for step_type in sorted(counts)]
        return f"Earlier steps summarized: {', '.join(parts)}."

    def _estimate_bytes(self, payload: Any) -> int:
        try:
            serialized = json.dumps(payload, ensure_ascii=False, default=str)
        except TypeError:
            serialized = str(payload)
        return len(serialized.encode("utf-8"))

    def _trim_context_for_llm(self, max_items: int = 50) -> None:
        """Keep only the most recent summaries to enforce deterministic caps."""
        if len(self.tool_summaries) > max_items:
            self.tool_summaries[:] = self.tool_summaries[-max_items:]
        if len(self.sandbox_summaries) > max_items:
            self.sandbox_summaries[:] = self.sandbox_summaries[-max_items:]
        if len(self.search_results) > max_items:
            self.search_results[:] = self.search_results[-max_items:]
            new_index: Dict[str, Dict[str, Any]] = {}
            for entry in self.search_results:
                key = self._search_key(entry)
                if key:
                    new_index[key] = entry
            self._search_index = new_index
        self._update_tool_menu()

    def redact_for_logs(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Redact sensitive fields from a payload before logging."""
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
        available_items = [entry for entry in self.search_results if entry.get("available")]
        menu: List[Dict[str, Any]] = []
        for entry in available_items[:limit]:
            provider = (entry.get("provider") or "").strip().lower()
            tool = (entry.get("tool") or "").strip().lower()
            if not provider or not tool:
                continue
            menu.append(
                {
                    "qualified_name": f"{provider}.{tool}",
                    "provider": provider,
                    "provider_path": f"sandbox_py/servers/{provider}",
                    "tool": tool,
                    "path": f"sandbox_py/servers/{provider}/{tool}.py",
                }
            )
        self.tool_menu = menu
