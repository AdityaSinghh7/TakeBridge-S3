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

# Essential tool keys to keep in slim LLM-facing view
ESSENTIAL_TOOL_KEYS = (
    "tool_id",
    "provider",
    "server",
    "call_signature",
    "description",
)


def _shallow_schema(schema: Dict[str, Any], *, max_depth: int = 2) -> Dict[str, Any]:
    """
    Return a shallow copy of a JSON-schema-like dict, truncating nested
    'properties' beyond max_depth. This keeps high-level keys and their types
    but avoids huge nested trees (Slack blocks, bot_profile, etc.).

    Args:
        schema: Full JSON schema dict (typically from output_schema)
        max_depth: Maximum depth to preserve nested properties (default: 2)

    Returns:
        Shallow schema dict with top-level keys + limited nesting
    """
    def _shallow(node: Any, depth: int) -> Any:
        if not isinstance(node, dict):
            return node
        result: Dict[str, Any] = {}
        for key, value in node.items():
            if key == "properties" and isinstance(value, dict):
                if depth >= max_depth:
                    # Keep only the property names and types, drop nested properties
                    props_summary = {}
                    for prop_name, prop_schema in value.items():
                        if isinstance(prop_schema, dict):
                            # Preserve type and basic structure, drop nested properties
                            summary = {}
                            if "type" in prop_schema:
                                summary["type"] = prop_schema["type"]
                            if "items" in prop_schema:
                                # For arrays, keep items but truncate nested properties
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
                # Handle array items - recurse but don't increment depth for items
                result[key] = _shallow(value, depth)
            elif key == "required" and isinstance(value, list):
                # Preserve required fields list
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
    """
    Flatten a JSON-schema-like `schema` into a list of 'path: type' strings.

    - Traverses deeply (no depth limit by default) but stops at `max_fields` entries.
    - Uses '[]' for array elements.
    - Uses dot notation for nested objects.

    Args:
        schema: Full JSON schema dict (typically from output_schema)
        prefix: Current path prefix (used internally for recursion)
        depth: Current depth (used internally for recursion)
        max_depth: Maximum depth to traverse (None = unlimited, default: None)
        max_fields: Maximum number of fields to include (default: 40)
        out: Output list (used internally for recursion)

    Returns:
        List of flattened field descriptions like ["messages[]: object", "messages[].messageId: string"]
    """
    if out is None:
        out = []
    
    if max_fields is not None and len(out) >= max_fields:
        return out
    
    # If we've hit depth limit, bail
    if max_depth is not None and depth > max_depth:
        return out
    
    # Only handle dict/object schemas
    if not isinstance(schema, dict):
        return out
    
    schema_type = schema.get("type")
    props = schema.get("properties", {})
    
    # Simple leaf: we've got a type and no child properties
    if schema_type and not props:
        if prefix:
            out.append(f"{prefix}: {schema_type}")
        return out
    
    # Traverse properties
    for name, subschema in props.items():
        if max_fields is not None and len(out) >= max_fields:
            break
        
        # Arrays: handle items as "name[]" etc
        if subschema.get("type") == "array":
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
    """
    Build a compact signature for the planner with only required arguments.

    Example:
      Entry with tool_id="gmail.gmail_search" and input_params.required=[{"name": "query"}]
      becomes: "gmail.gmail_search(query)"

    Args:
        entry: Full tool descriptor from search_tools()

    Returns:
        Minimal signature with only required arguments
    """
    tool_id = entry.get("tool_id")
    if not tool_id:
        # Fallback: provider.py_name
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
    """
    Strip Python type annotations from a signature string to reduce tokens.

    Example:
      'gmail.gmail_search(query: str, max_results: int = 20, ...)'
    becomes:
      'gmail.gmail_search(query, max_results=20, ...)'

    Args:
        sig: Function signature string with type annotations

    Returns:
        Simplified signature without type annotations
    """
    if not sig:
        return sig

    # Remove ": <type>" patterns, preserving everything else
    result = re.sub(r":\s*[^,)=]+", "", sig)
    
    # Normalize spaces around = signs (remove spaces around =)
    # This handles cases like "param = value" -> "param=value"
    result = re.sub(r"\s*=\s*", "=", result)
    
    return result


def _slim_tool_for_planner(entry: Dict[str, Any]) -> Dict[str, Any]:
    """
    Project a rich LLMToolDescriptor dict into a slimmer, LLM-facing view
    suitable for PLANNER_STATE_JSON. Keeps only fields that the planner
    prompt relies on, with flattened output fields.

    Args:
        entry: Full tool descriptor from search_tools()

    Returns:
        Slim tool descriptor with essential fields only
    """
    slim: Dict[str, Any] = {}

    # Core identity / selection
    for key in ESSENTIAL_TOOL_KEYS:
        if key in entry:
            slim[key] = entry[key]

    # Canonical sandbox import path (prefer explicit py_* when present)
    slim["py_module"] = entry.get("py_module") or entry.get("module")
    slim["py_name"] = entry.get("py_name") or entry.get("function")

    # Build minimal signature with only required arguments
    if "input_params" in entry:
        slim["call_signature"] = _build_minimal_signature(entry)
    else:
        # No structured params? Fall back to original signature or tool_id
        slim["call_signature"] = entry.get("call_signature") or entry.get("tool_id", "")

    # Inputs: structured params only (drop input_params_pretty)
    if "input_params" in entry:
        slim["input_params"] = entry["input_params"]

    # Outputs: flattened fields list (drop output_schema and output_schema_pretty)
    schema = entry.get("output_schema")
    if isinstance(schema, dict):
        slim["output_fields"] = _flatten_schema_fields(
            schema,
            max_depth=None,  # Unlimited depth
            max_fields=40,   # But capped at 40 fields
        )
    else:
        # Always include output_fields, even if empty
        slim["output_fields"] = []

    return slim


def _slim_provider_tree(tree: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Strip internal metadata from provider tree for LLM consumption.
    
    Only keeps provider name and list of available tool names.
    Discards: mcp_url, path, authorized, registered, configured, 
              tool_count, display_name, all_actions
    
    Args:
        tree: Full provider tree from list_providers()
    
    Returns:
        Minimal provider tree with only provider and tools fields
    """
    slim = []
    for node in tree:
        slim.append({
            "provider": node.get("provider"),
            "tools": node.get("available_tools", [])
        })
    return slim


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
    provider_tree: List[Dict[str, Any]] = field(default_factory=list)
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
        # Build trajectory from all steps (Action -> Observation pattern)
        trajectory: List[Dict[str, Any]] = []
        for step in self.steps:
            entry: Dict[str, Any] = {
                "step": step.index,
                "type": step.type,
                "reasoning": step.command.get("reasoning", "") if step.command else "",
                "action": step.command,  # The request
                "observation": step.output,  # The response
                "status": "success" if step.success else "failed",
            }
            trajectory.append(entry)
        
        # Slim search results for available_tools (detailed specs of discovered tools)
        available_tools = [_slim_tool_for_planner(e) for e in self.search_results]
        
        # Slim provider tree to remove internal metadata
        slim_tree = _slim_provider_tree(self.provider_tree)
        
        return {
            "task": self.task,
            "user_id": self.user_id,
            "run_id": self.run_id,
            "provider_tree": slim_tree,           # Cleaned provider tree (just names + tool lists)
            "available_tools": available_tools,   # Detailed specs of discovered tools
            "trajectory": trajectory              # History of Action -> Observation
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
