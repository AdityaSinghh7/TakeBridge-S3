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
from typing import Any, Callable, Dict, List, Literal, Optional
import hashlib
import json
import os
import re
import uuid

from shared.token_cost_tracker import TokenCostTracker
from shared.streaming import emit_event

from .budget import Budget, BudgetTracker, BudgetSnapshot
from .summarize import summarize_payload, redact_payload
from .prompts import PLANNER_PROMPT
from mcp_agent.knowledge.builder import get_index

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


def _flatten_schema_fields(
    schema: Dict[str, Any],
    *,
    prefix: str = "",
    depth: int = 0,
    max_depth: Optional[int] = None,
    max_fields: int = 40,
    out: Optional[List[str]] = None,
) -> List[str]:
    """Flatten a JSON-schema-like dict into a list of 'path: type' strings."""
    if out is None:
        out = []

    if max_fields is not None and len(out) >= max_fields:
        return out

    if max_depth is not None and depth > max_depth:
        return out

    if not isinstance(schema, dict):
        return out

    schema_type = schema.get("type")
    props = schema.get("properties", {})

    if schema_type and not props:
        if prefix:
            out.append(f"{prefix}: {schema_type}")
        return out

    for name, subschema in props.items():
        if max_fields is not None and len(out) >= max_fields:
            break

        if isinstance(subschema, dict) and subschema.get("type") == "array":
            item = subschema.get("items", {})
            child_prefix = f"{prefix}.{name}[]" if prefix else f"{name}[]"
            _flatten_schema_fields(
                item,
                prefix=child_prefix,
                depth=depth + 1,
                max_depth=max_depth,
                max_fields=max_fields,
                out=out,
            )
        else:
            child_prefix = f"{prefix}.{name}" if prefix else name
            _flatten_schema_fields(
                subschema,
                prefix=child_prefix,
                depth=depth + 1,
                max_depth=max_depth,
                max_fields=max_fields,
                out=out,
            )

    return out


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


def _slim_provider_tree(tree: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Remove heavy fields from provider tree for prompt payloads."""
    slim: List[Dict[str, Any]] = []
    for entry in tree:
        provider = {
            "provider": entry.get("provider"),
            "display_name": entry.get("display_name"),
            "authorized": entry.get("authorized"),
            "registered": entry.get("registered"),
            "configured": entry.get("configured"),
            "mcp_url": entry.get("mcp_url"),
            "tool_count": len(entry.get("tools", [])),
        }
        tool_names = []
        for tool in entry.get("tools", []):
            minimal = {
                key: tool.get(key)
                for key in ESSENTIAL_TOOL_KEYS
                if key in tool
            }
            minimal["call_signature"] = tool.get("call_signature") or _build_minimal_signature(tool)
            if "input_params" in tool:
                minimal["input_params"] = {
                    "required": tool["input_params"].get("required", []),
                    "optional": tool["input_params"].get("optional", []),
                }
            slim_schema = tool.get("output_schema")
            if slim_schema:
                minimal["output_schema"] = _shallow_schema(slim_schema)
            if "output_fields" in tool:
                minimal["output_fields"] = tool["output_fields"]
            elif "output_schema" in tool:
                minimal["output_fields"] = _flatten_schema_fields(tool["output_schema"])
            tool_names.append(minimal)
        provider["tools"] = tool_names
        slim.append(provider)
    return slim


def _slim_tool_for_planner(entry: Dict[str, Any]) -> Dict[str, Any]:
    """Return a slimmed-down tool descriptor for the planner prompt."""
    result = {key: entry.get(key) for key in ESSENTIAL_TOOL_KEYS if key in entry}
    result["qualified_name"] = entry.get("qualified_name") or entry.get("tool_id")
    result["server"] = entry.get("server") or entry.get("provider")
    result["py_module"] = entry.get("py_module") or entry.get("module")
    result["py_name"] = entry.get("py_name") or entry.get("function")
    result["call_signature"] = entry.get("call_signature") or _build_minimal_signature(entry)
    if "input_params" in entry:
        result["input_params"] = entry["input_params"]
    if "output_fields" in entry:
        result["output_fields"] = entry["output_fields"]
    elif "output_schema" in entry:
        result["output_fields"] = _flatten_schema_fields(entry["output_schema"])
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
    tool_menu: List[Dict[str, Any]] = field(default_factory=list)
    tool_summaries: List[Dict[str, Any]] = field(default_factory=list)
    sandbox_summaries: List[Dict[str, Any]] = field(default_factory=list)
    discovered_tools: Dict[str, Dict[str, Any]] = field(default_factory=dict)  # tool_id -> deep_view
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
        )
        self.history.append(step)
        return step

    def add_step(self, **kwargs) -> AgentStep:
        """Backwards-compatible alias for record_step."""
        return self.record_step(**kwargs)

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
            safe_payload = redact_payload(payload)
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
        self._update_tool_menu()
        if self.search_results:
            self.discovery_completed = True

    def add_search_results(self, results: List[Dict[str, Any]], *, replace: bool = False) -> None:
        """Backwards-compatible alias for merge_search_results."""
        self.merge_search_results(results, replace=replace)

    def set_search_results(self, results: List[Dict[str, Any]]) -> None:
        """Replace the current search results with the provided list."""
        self.merge_search_results(results, replace=True)

    def replace_search_results(self, results: List[Dict[str, Any]]) -> None:
        """Deprecated alias for set_search_results; preserved for compatibility."""
        self.set_search_results(results)

    def cache_tool_deep_view(self, tool_id: str, view: Dict[str, Any]) -> None:
        """Cache detailed tool specification after discovery."""
        self.discovered_tools[tool_id] = view

    def get_tool_deep_view(self, tool_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve cached tool specification."""
        return self.discovered_tools.get(tool_id)

    def has_discovered_tool(self, tool_id: str) -> bool:
        """Check if tool has been discovered."""
        return tool_id in self.discovered_tools

    def add_tool_summary(self, summary: Dict[str, Any]) -> None:
        self.tool_summaries.append(summary)
        self._trim_context_for_llm()

    def add_sandbox_summary(self, summary: Dict[str, Any]) -> None:
        self.sandbox_summaries.append(summary)
        self._trim_context_for_llm()

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

    def build_planner_state(self, _snapshot: BudgetSnapshot | None = None) -> Dict[str, Any]:
        """Build the planner_state JSON consumed by PlannerLLM."""
        trajectory: List[Dict[str, Any]] = []
        for step in self.history:
            entry: Dict[str, Any] = {
                "step": step.index,
                "type": step.type,
                "reasoning": step.command.get("reasoning", "") if step.command else "",
                "action": step.command,
                "observation": step.output,
                "status": "success" if step.success else "failed",
            }
            trajectory.append(entry)

        available_tools = [_slim_tool_for_planner(e) for e in self.search_results]
        slim_tree = _slim_provider_tree(self.provider_tree)

        return {
            "task": self.task,
            "user_id": self.user_id,
            "run_id": self.run_id,
            "provider_tree": slim_tree,
            "available_tools": available_tools,
            "trajectory": trajectory,
        }

    def planner_state(self, snapshot: BudgetSnapshot | None = None) -> Dict[str, Any]:
        """Deprecated alias for build_planner_state."""
        return self.build_planner_state(snapshot)

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
            "discovered_tools": self.discovered_tools,
            "history": [step.to_dict() for step in self.history],
            "raw_outputs": self.raw_outputs,
            "tool_summaries": self.tool_summaries,
            "sandbox_summaries": self.sandbox_summaries,
            "logs": self.logs,
            "finished": self.finished,
            "failed": self.failed,
            "failure_reason": self.failure_reason,
            "final_result": self.final_result,
        }
