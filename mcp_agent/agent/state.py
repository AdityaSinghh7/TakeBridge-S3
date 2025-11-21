"""Agent state management - pure data container for planning session.

This module provides AgentState, a focused state container that holds the
"memory" of the agent during execution. It handles:
- Execution history (thoughts, actions, observations)
- Tool discovery cache (inventory + deep views)
- Budget tracking
- Context window management

Separated from PlannerContext to enforce clear boundaries between:
- State (what we remember)
- Logic (how we process)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional
import hashlib
import json
import os
import re
import uuid

from shared.token_cost_tracker import TokenCostTracker
from shared.streaming import emit_event

from .budget import Budget, BudgetTracker, BudgetSnapshot
from .prompts import PLANNER_PROMPT
from mcp_agent.knowledge.builder import get_index


def _redact_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Simple payload redaction for logging (inline version)."""
    # Basic implementation - just return as-is for now
    # Could add keyword filtering if needed
    return payload


def _summarize_for_storage(
    label: str,
    payload: Any,
    *,
    purpose: str = "storage",
    storage_dir: Path | None = None,
    persist_payload: bool = False,
) -> Dict[str, Any]:
    """Simple storage summarization (inline version)."""
    # Minimal implementation - just truncate if too large
    import json
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

StepType = Literal["tool", "sandbox", "search", "finish", "fail"]

# Essential tool keys to keep in slim LLM-facing view
ESSENTIAL_TOOL_KEYS = (
    "tool_id",
    "provider",
    "server",
    "call_signature",
    "description",
)


def _shallow_schema(schema: Dict[str, Any], *, max_depth: int = 2) -> Dict[str, Any]:
    """Return a shallow copy of a JSON-schema-like dict, truncating nested properties."""

    def _shallow(node: Any, depth: int) -> Any:
        if not isinstance(node, dict):
            return node
        result: Dict[str, Any] = {}
        for key, value in node.items():
            if key == "properties" and isinstance(value, dict):
                if depth >= max_depth:
                    props_summary = {}
                    for prop_name, prop_schema in value.items():
                        if isinstance(prop_schema, dict):
                            summary = {}
                            if "type" in prop_schema:
                                summary["type"] = prop_schema["type"]
                            if "items" in prop_schema:
                                items_val = prop_schema["items"]
                                if isinstance(items_val, dict) and "type" in items_val:
                                    summary["items"] = {"type": items_val["type"]}
                                else:
                                    summary["items"] = {}
                            props_summary[prop_name] = summary
                        else:
                            props_summary[prop_name] = {}
                    result[key] = props_summary
                else:
                    result[key] = {
                        prop_name: _shallow(prop_schema, depth + 1)
                        for prop_name, prop_schema in value.items()
                    }
            elif key == "items" and isinstance(value, dict):
                result[key] = _shallow(value, depth)
            elif key == "required" and isinstance(value, list):
                result[key] = value
            else:
                result[key] = _shallow(value, depth)
        return result

    return _shallow(schema, depth=0)


def _build_minimal_signature(entry: Dict[str, Any]) -> str:
    """Build a compact signature for the planner with only required arguments."""
    tool_id = entry.get("tool_id")
    if not tool_id:
        provider = entry.get("provider", "tool")
        py_name = entry.get("py_name") or entry.get("function") or "call"
        tool_id = f"{provider}.{py_name}"

    params: Dict[str, Any] = entry.get("input_params") or {}
    required: List[Dict[str, Any]] = params.get("required") or []
    names = [p.get("name", "arg") for p in required]

    if names:
        joined = ", ".join(names)
        return f"{tool_id}({joined})"
    return f"{tool_id}()"


def _simplify_signature(sig: str) -> str:
    """Strip Python type annotations from a signature string to reduce tokens."""
    if not sig:
        return sig
    result = re.sub(r":\s*[^,)=]+", "", sig)
    result = re.sub(r"\s*=\s*", "=", result)
    return result


@dataclass
class AgentStep:
    """Single step in agent execution history."""

    index: int
    type: StepType
    command: Dict[str, Any]
    success: bool
    preview: str
    result_key: Optional[str] = None
    error: Optional[str] = None
    output: Any = None
    is_summary: bool = False
    is_smart_summary: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for serialization."""
        return {
            "index": self.index,
            "type": self.type,
            "command": self.command,
            "success": self.success,
            "preview": self.preview,
            "result_key": self.result_key,
            "error": self.error,
            "output": self.output,
            "is_summary": self.is_summary,
            "is_smart_summary": self.is_smart_summary,
        }


@dataclass
class AgentState:
    """Planning session state - the 'memory' of the agent.

    This is a pure data container focused on what the agent remembers:
    - What has been done (history)
    - What tools are available (inventory)
    - What tools have been discovered (discovered_tools)
    - How much budget remains (budget_tracker)

    Responsibilities:
    - Store execution history
    - Cache discovered tool details
    - Track budget consumption
    - Manage context window (trim old steps when needed)

    NOT responsible for:
    - Executing actions (see executor.py)
    - Making decisions (see orchestrator.py)
    - Formatting prompts (see prompts.py)
    """

    # Core identity
    task: str
    user_id: str
    request_id: str

    # Budget constraints
    budget: Budget
    budget_tracker: BudgetTracker = field(init=False)
    token_tracker: TokenCostTracker = field(default_factory=TokenCostTracker)

    # Additional context + identifiers
    extra_context: Dict[str, Any] = field(default_factory=dict)
    planner_prompt: str = PLANNER_PROMPT
    run_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    task_id: str = field(init=False)

    # Discovery state
    provider_tree: List[Dict[str, Any]] = field(default_factory=list)
    search_results: List[Dict[str, Any]] = field(default_factory=list)
    discovery_completed: bool = False

    # Execution history
    history: List[AgentStep] = field(default_factory=list)
    logs: List[Dict[str, Any]] = field(default_factory=list)

    # Raw outputs from tools/sandbox (for detailed inspection)
    raw_outputs: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)

    # Terminal state
    finished: bool = False
    failed: bool = False
    failure_reason: Optional[str] = None
    final_result: Any = None

    # Summary storage
    summary_root: Path = field(init=False)
    summary_threshold_bytes: int = field(default=16_000)
    summary_item_limit: int = field(default=50)

    # Internal helpers
    _search_index: Dict[str, Dict[str, Any]] = field(init=False, default_factory=dict)
    _persist_summaries: bool = field(init=False)

    def __post_init__(self):
        """Initialize derived fields."""
        self.budget_tracker = BudgetTracker(self.budget)
        if self.request_id:
            self.run_id = self.request_id
        self.task_id = self._generate_task_id()
        self.summary_root = self._init_summary_root()
        self._search_index = {}
        self._persist_summaries = os.getenv("MCP_SUMMARY_ALWAYS_PERSIST", "").lower() in {
            "1",
            "true",
            "yes",
            "on",
        }

    # --- History management ---

    def record_step(
        self,
        *,
        type: StepType,
        command: Dict[str, Any],
        success: bool,
        preview: str,
        result_key: Optional[str] = None,
        error: Optional[str] = None,
        output: Any = None,
        is_summary: bool = False,
        is_smart_summary: bool = False,
    ) -> AgentStep:
        """Add a step to execution history."""
        step = AgentStep(
            index=len(self.history),
            type=type,
            command=command,
            success=success,
            preview=preview[:200],  # Truncate long previews
            result_key=result_key,
            error=error,
            output=output,
            is_summary=is_summary,
            is_smart_summary=is_smart_summary,
        )
        self.history.append(step)
        return step

    def get_context_window(self, max_steps: Optional[int] = None) -> List[AgentStep]:
        """Get recent history within limits.

        Args:
            max_steps: Maximum number of steps to return (None = all)

        Returns:
            List of recent steps (oldest first)
        """
        if max_steps is None or max_steps <= 0:
            return self.history
        return self.history[-max_steps:]

    # --- Logging & telemetry ---

    def record_event(self, event: str, payload: Dict[str, Any]) -> None:
        """Record a planner event (mirrors legacy PlannerContext semantics)."""
        try:
            safe_payload = _redact_payload(payload)
        except Exception:
            safe_payload = payload
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

    # --- Tool discovery cache ---

    def merge_search_results(self, results: List[Dict[str, Any]], *, replace: bool = False) -> None:
        """Merge new search results, keeping highest scores per tool."""
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
        if self.search_results:
            self.discovery_completed = True

    def resolve_mcp_tool_name(self, provider: str, tool_name: str) -> str:
        """Resolve provider/tool pair to the underlying MCP tool name."""
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

    # --- Raw output storage ---

    def append_raw_output(self, key: str, entry: Dict[str, Any]) -> Dict[str, Any]:
        """Append raw output entry for detailed inspection."""
        if key not in self.raw_outputs:
            self.raw_outputs[key] = []
        self.raw_outputs[key].append(entry)
        return entry

    def get_raw_outputs(self, key: str) -> List[Dict[str, Any]]:
        """Retrieve raw outputs by key."""
        return self.raw_outputs.get(key, [])

    # --- Summaries & redaction ---

    def summarize_tool_output(
        self,
        label: str,
        payload: Any,
        *,
        purpose: str = "for_planning",
        force: bool = False,
    ) -> Dict[str, Any]:
        """Summarize tool output for logging/storage purposes."""
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
        """Summarize sandbox output for logging/storage purposes."""
        return self._summarize_and_record(
            label,
            payload,
            purpose=purpose,
            storage_subdir="sandbox",
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
        force: bool = False,
    ) -> Dict[str, Any]:
        """Summarize payload and log the event (no longer stores in separate lists)."""
        if not force and not self.should_summarize(payload):
            return {}
        storage_dir = self.summary_root / storage_subdir
        summary = _summarize_for_storage(
            label,
            payload,
            purpose=purpose,
            storage_dir=storage_dir,
            persist_payload=self._persist_summaries,
        )
        # Note: We no longer store summaries in separate lists (tool_summaries, sandbox_summaries)
        # as they were redundant. Summaries are logged via events and stored in files if needed.
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

    def _estimate_bytes(self, payload: Any) -> int:
        try:
            serialized = json.dumps(payload, ensure_ascii=False, default=str)
        except TypeError:
            serialized = str(payload)
        return len(serialized.encode("utf-8"))

    def _trim_context_for_llm(self, max_items: int = 50) -> None:
        """Keep only the most recent search results to enforce deterministic caps."""
        if len(self.search_results) > max_items:
            self.search_results[:] = self.search_results[-max_items:]
            # Rebuild search index after trimming
            new_index: Dict[str, Dict[str, Any]] = {}
            for entry in self.search_results:
                key = self._search_key(entry)
                if key:
                    new_index[key] = entry
            self._search_index = new_index

    def _search_key(self, entry: Dict[str, Any]) -> Optional[str]:
        """Extract unique key for deduplication (supports both legacy and compact formats)."""
        # Prefer tool_id (compact format)
        tool_id = entry.get("tool_id")
        if tool_id:
            return tool_id

        # Fall back to qualified_name (legacy format)
        qualified_name = entry.get("qualified_name")
        if qualified_name:
            return qualified_name

        # Last resort: construct from provider.tool (legacy format)
        provider = (entry.get("provider") or "").strip().lower()
        tool = (entry.get("tool") or "").strip().lower()
        if provider and tool:
            return f"{provider}.{tool}"

        return None

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

    # --- Terminal state management ---

    def is_terminal(self) -> bool:
        """Check if agent has reached terminal state."""
        return self.finished or self.failed

    def mark_finished(self, result: Any) -> None:
        """Mark execution as successfully finished."""
        self.finished = True
        self.final_result = result

    def mark_failed(self, reason: str) -> None:
        """Mark execution as failed."""
        self.failed = True
        self.failure_reason = reason

    # --- Budget checks ---

    def is_budget_exhausted(self) -> bool:
        """Check if any budget limit has been exceeded."""
        snapshot = self.budget_tracker.snapshot()
        return (
            snapshot.steps_taken >= snapshot.max_steps
            or snapshot.tool_calls >= snapshot.max_tool_calls
            or snapshot.code_runs >= snapshot.max_code_runs
            or snapshot.estimated_llm_cost_usd >= snapshot.max_llm_cost_usd
        )

    def get_budget_snapshot(self) -> Dict[str, Any]:
        """Get current budget state as dict."""
        snapshot = self.budget_tracker.snapshot()
        return {
            "steps_taken": snapshot.steps_taken,
            "tool_calls": snapshot.tool_calls,
            "code_runs": snapshot.code_runs,
            "estimated_llm_cost_usd": snapshot.estimated_llm_cost_usd,
            "max_steps": snapshot.max_steps,
            "max_tool_calls": snapshot.max_tool_calls,
            "max_code_runs": snapshot.max_code_runs,
            "max_llm_cost_usd": snapshot.max_llm_cost_usd,
        }

    # --- Prompt state ---

    def _summarize_search_observation(self, observation: Dict[str, Any]) -> str:
        """
        Summarize search results: store tool_ids only, not full descriptors.

        This prevents duplication - the full tool specs are in available_tools.
        """
        if not observation:
            return "Search returned no results"

        found_tools = observation.get("found_tools", [])
        if not found_tools:
            return "Search returned no results"

        tool_ids = [t.get("tool_id", "unknown") for t in found_tools]
        count = len(tool_ids)

        if count <= 3:
            return f"Found {count} tools: {', '.join(tool_ids)}"
        else:
            return f"Found {count} tools: {', '.join(tool_ids[:3])}, ..."

    def _summarize_tool_observation(self, observation: Dict[str, Any]) -> str:
        """
        Summarize tool execution results: key fields only.

        Full results are stored in raw_outputs if needed for reference.
        """
        if not observation:
            return "No output"

        # Check if it's a successful result
        if isinstance(observation, dict):
            if observation.get("error"):
                error_msg = str(observation.get("error", "Unknown error"))
                return f"Error: {error_msg[:100]}"

            if "successful" in observation:
                if not observation["successful"]:
                    error_msg = observation.get("error", "Unknown failure")
                    return f"Failed: {error_msg[:100]}"

                # Summarize successful data
                data = observation.get("data", {})
                return self._summarize_data_payload(data)

        # Fall back to generic summarization
        return self._summarize_data_payload(observation)

    def _summarize_sandbox_observation(self, observation: Dict[str, Any]) -> str:
        """
        Format sandbox execution results for trajectory.

        Unlike tool calls, sandbox code is expected to return compact summaries,
        so we show the full return value (up to reasonable limit) rather than
        summarizing further.
        """
        if not observation:
            return "No output"

        # Check for errors
        if isinstance(observation, dict):
            if observation.get("error"):
                error_msg = str(observation.get("error", "Unknown error"))
                return f"Error: {error_msg[:200]}"

            # Show the full result/return value from sandbox code
            # The code should already be returning compact summaries
            if "result" in observation:
                result = observation["result"]
                # Return full result up to 1000 chars (sandbox should keep it compact)
                result_str = str(result) if not isinstance(result, str) else result
                if len(result_str) <= 1000:
                    return result_str
                else:
                    return result_str[:997] + "..."

            # If no result field, show success status
            if observation.get("successful"):
                return "Execution completed successfully"

        # Fallback to string representation
        obs_str = str(observation)
        return obs_str[:1000] if len(obs_str) <= 1000 else obs_str[:997] + "..."

    def _summarize_data_payload(self, data: Any, max_chars: int = 500) -> str:
        """
        Smart data summarization showing actual values, not just structure.

        For tool call results, we want the model to see:
        - Array lengths (e.g., "messages: 0 items")
        - Numeric values (e.g., "resultSizeEstimate: 0")
        - Short strings (e.g., "status: active")
        - Text previews (e.g., "body: Hello world...")

        This allows the model to understand what actually happened without
        seeing full payloads.
        """
        if data is None:
            return "null"

        if isinstance(data, bool):
            return str(data)

        if isinstance(data, (int, float)):
            return str(data)

        if isinstance(data, str):
            if len(data) == 0:
                return '""'
            elif len(data) <= 100:
                return f'"{data}"'
            else:
                return f'"{data[:97]}..."'

        if isinstance(data, list):
            count = len(data)
            if count == 0:
                return "[]"
            elif count == 1:
                item_summary = self._summarize_data_payload(data[0], max_chars=100)
                return f"[{item_summary}]"
            else:
                first_summary = self._summarize_data_payload(data[0], max_chars=80)
                return f"[{count} items, first: {first_summary}]"

        if isinstance(data, dict):
            if not data:
                return "{}"

            # Build smart key-value summaries
            parts = []
            chars_used = 0

            for key, value in data.items():
                # Summarize the value intelligently
                if isinstance(value, list):
                    val_str = f"{len(value)} items" if value else "[]"
                elif isinstance(value, dict):
                    val_str = f"{len(value)} keys" if value else "{}"
                elif isinstance(value, str):
                    if len(value) == 0:
                        val_str = '""'
                    elif len(value) <= 50:
                        val_str = f'"{value}"'
                    else:
                        val_str = f'"{value[:47]}..."'
                elif isinstance(value, (int, float, bool)):
                    val_str = str(value)
                elif value is None:
                    val_str = "null"
                else:
                    val_str = f"{type(value).__name__}"

                part = f"{key}: {val_str}"
                if chars_used + len(part) + 2 > max_chars:
                    parts.append("...")
                    break

                parts.append(part)
                chars_used += len(part) + 2  # +2 for ", "

            return "{" + ", ".join(parts) + "}"

        return f"{type(data).__name__} object"

    def build_planner_state(self, _snapshot: BudgetSnapshot | None = None) -> Dict[str, Any]:
        """
        Build the planner_state JSON consumed by PlannerLLM.

        This is the ONLY place where tool specifications appear in full.
        Trajectory entries contain only summaries to minimize context usage.
        """
        trajectory: List[Dict[str, Any]] = []
        for step in self.history:
            entry: Dict[str, Any] = {
                "step": step.index,
                "type": step.type,
                "reasoning": step.command.get("reasoning", "") if step.command else "",
                "status": "success" if step.success else "failed",
            }

            # Add summarized observation instead of full output
            if step.type == "search":
                entry["summary"] = self._summarize_search_observation(step.output)
            elif step.type == "tool":
                tool_id = step.command.get("tool_id", "unknown") if step.command else "unknown"
                entry["tool_id"] = tool_id
                entry["summary"] = step.output
            elif step.type == "sandbox":
                entry["summary"] = step.output
            elif step.type in ("finish", "fail"):
                # For finish/fail steps, include minimal info
                entry["summary"] = step.preview or "Step completed"
            else:
                # Generic fallback
                entry["summary"] = step.preview or "No summary"

            trajectory.append(entry)

        # available_tools is the SINGLE SOURCE OF TRUTH for tool specs
        # Compact descriptors are already minimal, just pass through
        available_tools = self.search_results

        # provider_tree is already slim from inventory view
        slim_tree = self.provider_tree

        return {
            "task": self.task,
            "user_id": self.user_id,
            "run_id": self.run_id,
            "provider_tree": slim_tree,
            "available_tools": available_tools,
            "trajectory": trajectory,
        }

    # --- Serialization ---

    def to_dict(self) -> Dict[str, Any]:
        """Convert state to dict for serialization."""
        return {
            "task": self.task,
            "user_id": self.user_id,
            "request_id": self.request_id,
            "run_id": self.run_id,
            "task_id": self.task_id,
            "budget": self.get_budget_snapshot(),
            "provider_tree": self.provider_tree,
            "search_results": self.search_results,
            "history": [step.to_dict() for step in self.history],
            "raw_outputs": self.raw_outputs,
            "logs": self.logs,
            "finished": self.finished,
            "failed": self.failed,
            "failure_reason": self.failure_reason,
            "final_result": self.final_result,
        }
