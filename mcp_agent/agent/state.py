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
from typing import Any, Dict, List, Optional
import hashlib
import re
import uuid

from shared.token_cost_tracker import TokenCostTracker
from shared.streaming import emit_event

from .budget import Budget, BudgetTracker, BudgetSnapshot
from .prompts import PLANNER_PROMPT
from .history import ExecutionHistory, AgentStep, StepType
from .tool_cache import ToolCache
from .summary_manager import SummaryManager


def _redact_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Simple payload redaction for logging (inline version)."""
    # Basic implementation - just return as-is for now
    # Could add keyword filtering if needed
    return payload

@dataclass
class AgentState:
    """Planning session state - the 'memory' of the agent.

    This is a pure data container focused on what the agent remembers:
    - What has been done (history)
    - What tools are available (inventory)
    - What tools have been discovered (discovered_tools)
    - How much budget remains (budget_tracker)

    Responsibilities:
    - Coordinate execution history (delegates to ExecutionHistory)
    - Coordinate tool cache (delegates to ToolCache)
    - Coordinate output summarization (delegates to SummaryManager)
    - Track budget consumption
    - Manage provider inventory

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

    # Tool constraints for provider filtering
    tool_constraints: Optional[Dict[str, Any]] = None

    # Provider inventory (lightweight tree view)
    provider_tree: List[Dict[str, Any]] = field(default_factory=list)

    # Logs and telemetry
    logs: List[Dict[str, Any]] = field(default_factory=list)

    # Raw outputs from tools/sandbox (for detailed inspection)
    raw_outputs: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)

    # Terminal state
    finished: bool = False
    failed: bool = False
    failure_reason: Optional[str] = None
    final_result: Any = None

    # Delegated components (initialized in __post_init__)
    _execution_history: ExecutionHistory = field(init=False)
    _tool_cache: ToolCache = field(init=False)
    _summary_manager: SummaryManager = field(init=False)

    def __post_init__(self):
        """Initialize derived fields and delegated components."""
        self.budget_tracker = BudgetTracker(self.budget)
        if self.request_id:
            self.run_id = self.request_id
        self.task_id = self._generate_task_id()

        # Initialize delegated components
        self._execution_history = ExecutionHistory()
        self._tool_cache = ToolCache(max_cached_tools=50)
        self._summary_manager = SummaryManager(
            task_id=self.task_id,
            event_recorder=self.record_event,
            summary_threshold_bytes=16_000,
            summary_item_limit=50,
        )

    # --- Properties for delegated components ---

    @property
    def history(self) -> List[AgentStep]:
        """Get execution history (delegates to ExecutionHistory)."""
        return self._execution_history.history

    @property
    def search_results(self) -> List[Dict[str, Any]]:
        """Get search results (delegates to ToolCache)."""
        return self._tool_cache.search_results

    @property
    def discovery_completed(self) -> bool:
        """Check if tool discovery is completed (delegates to ToolCache)."""
        return self._tool_cache.discovery_completed

    @discovery_completed.setter
    def discovery_completed(self, value: bool) -> None:
        """Set discovery completion status (delegates to ToolCache)."""
        self._tool_cache._discovery_completed = value

    # --- History management (delegates to ExecutionHistory) ---

    def record_step(
        self,
        *,
        action_type: StepType,
        success: bool,
        action_reasoning: str,
        action_input: Dict[str, Any],
        action_outcome: Dict[str, Any],
        error: Optional[str] = None,
        is_smart_summary: bool = False,
        observation: Optional[Any] = None,
        observation_metadata: Optional[Dict[str, Any]] = None,
    ) -> AgentStep:
        """Add a canonical step to execution history (delegates to ExecutionHistory)."""
        return self._execution_history.record_step(
            action_type=action_type,
            success=success,
            action_reasoning=action_reasoning,
            action_input=action_input,
            action_outcome=action_outcome,
            error=error,
            is_smart_summary=is_smart_summary,
            observation=observation,
            observation_metadata=observation_metadata,
        )

    def get_context_window(self, max_steps: Optional[int] = None) -> List[AgentStep]:
        """Get recent history within limits (delegates to ExecutionHistory).

        Args:
            max_steps: Maximum number of steps to return (None = all)

        Returns:
            List of recent steps (oldest first)
        """
        return self._execution_history.get_context_window(max_steps)

    # --- Logging & telemetry ---

    def record_event(self, event: str, payload: Dict[str, Any]) -> None:
        """Record a planner event."""
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

    # --- Tool discovery cache (delegates to ToolCache) ---

    def merge_search_results(self, results: List[Dict[str, Any]], *, replace: bool = False) -> None:
        """Merge new search results, keeping highest scores per tool (delegates to ToolCache)."""
        self._tool_cache.merge_search_results(results, replace=replace)

    def resolve_mcp_tool_name(self, provider: str, tool_name: str) -> str:
        """Resolve provider/tool pair to the underlying MCP tool name (delegates to ToolCache)."""
        return self._tool_cache.resolve_mcp_tool_name(self.user_id, provider, tool_name)

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

    # --- Summaries & redaction (delegates to SummaryManager) ---

    def summarize_tool_output(
        self,
        label: str,
        payload: Any,
        *,
        purpose: str = "for_planning",
        force: bool = False,
    ) -> Dict[str, Any]:
        """Summarize tool output for logging/storage purposes (delegates to SummaryManager)."""
        return self._summary_manager.summarize_tool_output(
            label, payload, purpose=purpose, force=force
        )

    def summarize_sandbox_output(
        self,
        label: str,
        payload: Any,
        *,
        purpose: str = "for_planning",
        force: bool = False,
    ) -> Dict[str, Any]:
        """Summarize sandbox output for logging/storage purposes (delegates to SummaryManager)."""
        return self._summary_manager.summarize_sandbox_output(
            label, payload, purpose=purpose, force=force
        )

    def should_summarize(self, payload: Any) -> bool:
        """Check if payload needs summarization (delegates to SummaryManager)."""
        return self._summary_manager.should_summarize(payload)

    # --- Helper methods ---

    def _generate_task_id(self) -> str:
        """Generate unique task ID from user_id and task."""
        digest = hashlib.sha1(f"{self.user_id}:{self.task}".encode("utf-8")).hexdigest()[:10]
        base = re.sub(r"[^a-zA-Z0-9_-]", "-", self.user_id).strip("-") or "task"
        return f"{base}-{digest}"

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

    # --- Planner state building ---

    def build_planner_state(self, _snapshot: BudgetSnapshot | None = None) -> Dict[str, Any]:
        """Build the planner_state JSON consumed by PlannerLLM.

        This is the ONLY place where tool specifications appear in full.
        Trajectory entries contain only summaries to minimize context usage.
        Delegates trajectory building to ExecutionHistory.
        """
        # Build trajectory (delegates to ExecutionHistory)
        trajectory = self._execution_history.build_trajectory()

        # available_tools is the SINGLE SOURCE OF TRUTH for tool specs
        # Compact descriptors are already minimal, just pass through.
        available_tools = list(self.search_results or [])

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

    # --- Markdown trajectory generation for orchestrator ---

    def build_markdown_trajectory(self) -> str:
        """Build COMPLETE self-contained markdown trajectory for orchestrator.

        CRITICAL: This trajectory must contain ALL relevant data.
        NO raw outputs or telemetry should be needed - everything is in this markdown.

        Returns:
            Rich markdown trajectory showing all steps with complete data
        """
        import json

        lines = []

        for step in self._execution_history.history:
            step_type = step.action_type
            step_num = step.action_step + 1  # 1-based for readability

            if step_type == "search":
                # Extract search info
                action_input = step.action_input
                query = action_input.get("search_query", "")
                provider = action_input.get("provider", "")

                # Get found tools from observation
                observation = step.observation or []
                tool_count = 0
                tool_names: List[str] = []
                if isinstance(step.action_outcome, dict):
                    tool_count = step.action_outcome.get("total_found", 0) or 0
                    names = step.action_outcome.get("found_tool_names")
                    if isinstance(names, list):
                        tool_names = [n for n in names if isinstance(n, str) and n]
                if tool_count == 0 and isinstance(observation, list):
                    tool_count = len(observation)

                lines.append(f"### Step {step_num}: Search - {provider}")
                lines.append(f"**Query**: {query}")
                lines.append(f"**Found**: {tool_count} tool(s)")

                if tool_names:
                    lines.append("**Tools**:")
                    for name in tool_names[:20]:
                        lines.append(f"- `{name}`")
                elif tool_count > 0 and isinstance(observation, list):
                    lines.append("**Tools**:")
                    for tool in observation[:20]:  # Limit to first 20 tools
                        tool_id = tool.get("tool_id", "unknown")
                        tool_desc = tool.get("description", "")[:150]  # Limit description length
                        lines.append(f"- `{tool_id}`: {tool_desc}")

                if not step.success and step.error:
                    lines.append(f"**Error**: {step.error}")

            elif step_type == "tool":
                # Extract tool info
                action_input = step.action_input
                tool_id = action_input.get("tool_id", "unknown")
                args = action_input.get("args", {})

                lines.append(f"### Step {step_num}: Tool Call - {tool_id}")

                args_json = json.dumps(args, indent=2, ensure_ascii=False)
                lines.append(f"**Arguments**:\n```json\n{args_json}\n```")

                if step.success:
                    # Show unwrapped response
                    observation = step.observation
                    if observation is not None:
                        obs_json = json.dumps(observation, indent=2, ensure_ascii=False)
                        lines.append(f"**Response**:\n```json\n{obs_json}\n```")

                    # Note if smart summary was used
                    if step.is_smart_summary:
                        lines.append("*(Response summarized via LLM)*")
                else:
                    lines.append(f"**Error**: {step.error or 'Unknown error'}")

            elif step_type == "inspect_tool_output":
                action_input = step.action_input
                tool_id = action_input.get("tool_id", "unknown")
                field_path = action_input.get("field_path", "") or ""
                max_depth = action_input.get("max_depth", "")
                max_fields = action_input.get("max_fields", "")

                lines.append(f"### Step {step_num}: Inspect Tool Output - {tool_id}")
                lines.append(f"**Field Path**: {field_path or '(root)'}")
                if max_depth or max_fields:
                    lines.append(f"**Limits**: max_depth={max_depth}, max_fields={max_fields}")

                observation = step.observation
                if observation is not None:
                    obs_json = json.dumps(observation, indent=2, ensure_ascii=False)
                    lines.append(f"**Observation**:\n```json\n{obs_json}\n```")

                if step.success:
                    if step.is_smart_summary:
                        lines.append("*(Observation summarized via LLM)*")
                else:
                    lines.append(f"**Error**: {step.error or 'Unknown error'}")

            elif step_type == "sandbox":
                # Extract sandbox info
                action_input = step.action_input
                code = action_input.get("sandbox_code", "")

                lines.append(f"### Step {step_num}: Sandbox Execution")

                lines.append(f"**Code**:\n```python\n{code}\n```")

                if step.success:
                    # Show output
                    observation = step.observation
                    if observation:
                        if isinstance(observation, dict):
                            result_data = observation.get("result") or observation.get("data") or observation
                        else:
                            result_data = observation

                        result_json = json.dumps(result_data, indent=2, ensure_ascii=False)
                        lines.append(f"**Output**:\n```json\n{result_json}\n```")

                    # Note if smart summary was used
                    if step.is_smart_summary:
                        lines.append("*(Output summarized via LLM)*")
                else:
                    lines.append(f"**Error**: {step.error or 'Unknown error'}")
                    # Include the sandbox failure observation payload so the translator/planner
                    # can see the real underlying error, logs, and traceback (if present).
                    observation = step.observation
                    if observation is not None:
                        obs_render = observation
                        if isinstance(observation, dict):
                            obs_render = dict(observation)
                            tb = obs_render.get("traceback")
                            if isinstance(tb, str) and len(tb) > 4000:
                                obs_render["traceback"] = "... (truncated) ...\n" + tb[-4000:]
                            logs = obs_render.get("logs")
                            if isinstance(logs, list) and len(logs) > 50:
                                obs_render["logs"] = logs[:50] + ["... (truncated)"]

                        obs_json = json.dumps(obs_render, indent=2, ensure_ascii=False, default=str)
                        lines.append(f"**Observation**:\n```json\n{obs_json}\n```")

            elif step_type in ("finish", "fail"):
                # Extract completion info
                action_outcome = step.action_outcome
                summary = action_outcome.get("final_summary") or action_outcome.get("summary", "")
                reasoning = step.action_reasoning

                step_label = "Completion" if step_type == "finish" else "Failure"
                lines.append(f"### Step {step_num}: {step_label}")
                lines.append(f"**Reasoning**: {reasoning}")
                lines.append(f"**Summary**: {summary}")

                if not step.success or step.error:
                    lines.append(f"**Error**: {step.error or 'Task failed'}")

            lines.append("")  # Blank line between steps

        return "\n".join(lines)

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
            "history": self._execution_history.to_dict(),
            "raw_outputs": self.raw_outputs,
            "logs": self.logs,
            "finished": self.finished,
            "failed": self.failed,
            "failure_reason": self.failure_reason,
            "final_result": self.final_result,
        }
