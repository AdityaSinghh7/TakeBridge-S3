from __future__ import annotations

import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, Optional

from mcp_agent.core.context import AgentContext
from mcp_agent.env_sync import ensure_env_for_provider
from mcp_agent.user_identity import normalize_user_id
from mcp_agent.sandbox.ephemeral import generate_ephemeral_toolbox

from .budget import Budget
from .llm import PlannerLLM
from .parser import parse_planner_command
from .state import AgentState
from .types import MCPTaskResult, StepResult
from .executor import ActionExecutor


class AgentOrchestrator:
    """Coordinator for the high-level planner loop."""

    def __init__(
        self,
        agent_context: AgentContext,
        agent_state: AgentState,
        llm: PlannerLLM | None = None,
    ) -> None:
        self.agent_context = agent_context
        self.agent_state = agent_state
        self.llm = llm or PlannerLLM()
        self._executor = ActionExecutor(self.agent_context, self.agent_state)

    def run(self) -> MCPTaskResult:
        """
        Execute the planner loop until a terminal result is produced.

        Flow:
          1. Ensure the planner LLM is enabled.
          2. Load provider topology (high-level overview only).
          3. Repeatedly:
             - Check budget limits.
             - Ask the LLM for the next command and parse it.
             - Dispatch the command to the appropriate handler.
        """
        failure = self._ensure_llm_enabled()
        if failure:
            return failure

        self._load_inventory()

        while True:
            failure = self._check_budget()
            if failure:
                return failure

            self.agent_state.budget_tracker.steps_taken += 1
            command, failure = self._next_command()
            if failure:
                return failure
            result = self._dispatch_command(command)
            if result is not None:
                return result

    def _ensure_llm_enabled(self) -> MCPTaskResult | None:
        """Verify that the planner LLM is enabled before starting the loop."""
        llm_enabled = True
        is_enabled = getattr(self.llm, "is_enabled", None)
        if callable(is_enabled):
            try:
                llm_enabled = bool(is_enabled())
            except Exception:
                llm_enabled = True
        if not llm_enabled:
            return self._failure("planner_llm_disabled", "Planner LLM is disabled.")
        return None

    def _load_inventory(self) -> None:
        from mcp_agent.knowledge.search import get_inventory_view

        inventory = get_inventory_view(self.agent_context)
        providers = inventory.get("providers", []) if isinstance(inventory, dict) else inventory
        self.agent_state.provider_tree = providers
        self.agent_state.discovery_completed = True

    def _next_command(self) -> tuple[Dict[str, Any] | None, MCPTaskResult | None]:
        """
        Ask the LLM for the next planner command and parse it.

        Handles empty-response retries and converts protocol/shape errors into a
        terminal planner failure.
        """
        llm_result = self.llm.generate_plan(self.agent_state)
        text = llm_result.get("text") or ""
        if not text:
            self.agent_state.record_event(
                "mcp.llm.retry_empty",
                {"model": self.llm.model},
            )
            llm_result = self.llm.generate_plan(self.agent_state)
            text = llm_result.get("text") or ""
        try:
            return parse_planner_command(text), None
        except ValueError as exc:
            # Protocol/shape error in planner output.
            self.agent_state.record_event(
                "mcp.planner.protocol_error",
                {
                    "error": str(exc),
                    "raw_preview": text[:200],
                },
            )
            result = self._failure("planner_parse_error", str(exc), preview=text)
            return None, result

    def _dispatch_command(self, command: Dict[str, Any]) -> MCPTaskResult | None:
        """
        Route a parsed planner command to the appropriate execution path.

        Returns a terminal MCPTaskResult when the planner should stop, or None
        when the loop should continue.
        """
        cmd_type = command["type"]
        if cmd_type in {"search", "tool", "sandbox"}:
            result = self._executor.execute_step(command)
            return self._handle_action_result(command, result)

        if cmd_type == "finish":
            self._executor.execute_step(command)
            summary = command.get("summary") or "Task completed."
            reasoning = command.get("reasoning") or ""
            self.agent_state.record_step(
                type="finish",
                command=command,
                success=True,
                preview=reasoning or summary,
                output={"summary": summary},
                is_summary=False,
            )
            return self._success_result(summary)

        if cmd_type == "fail":
            self._executor.execute_step(command)
            reason_text = command.get("reason") or "Planner reported a failure."
            self.agent_state.record_step(
                type="fail",
                command=command,
                success=False,
                preview=reason_text,
                error=reason_text,
                output={"error": reason_text},
                is_summary=False,
            )
            return self._failure("planner_fail_action", reason_text, preview=str(command))

        return self._failure(
            "planner_unknown_command",
            "Unsupported planner command.",
            preview=str(command),
        )

    def _handle_action_result(self, command: Dict[str, Any], result: StepResult) -> MCPTaskResult | None:
        """Apply executor results to planner state."""
        cmd_type = command["type"]
        observation = result.observation or {}
        error_message = observation.get("error") or result.preview

        if cmd_type == "search":
            if not result.success:
                return self._failure(result.error_code or "search_failed", error_message, preview=str(command))
            query = (command.get("query") or "").strip()
            found_tools = observation.get("found_tools", [])
            self.agent_state.merge_search_results(found_tools, replace=False)
            # found_tools are already compact - no need to slim further
            self.agent_state.record_event(
                "mcp.search.completed",
                {
                    "query": query[:200],
                    "detail_level": "full",
                    "result_count": len(found_tools),
                    "tool_ids": [r.get("tool_id") for r in found_tools if r.get("tool_id")],
                },
            )
            reasoning = command.get("reasoning") or result.preview
            self.agent_state.record_step(
                type="search",
                command=command,
                success=True,
                preview=reasoning or f"Search '{query}' returned {len(found_tools)} results",
                output={"found_tools": found_tools},
                is_summary=False,
            )
            return None

        if cmd_type == "tool":
            if not result.success:
                self.agent_state.record_step(
                    type="tool",
                    command=command,
                    success=False,
                    preview=error_message,
                    result_key=result.raw_output_key,
                    error=result.error_code or result.error or "tool_execution_failed",
                    output=observation,
                    is_summary=False,
                )
                return self._failure(
                    result.error_code or "tool_execution_failed",
                    error_message,
                    preview=str(command),
                    recorded_step=True,
                )
            reasoning = command.get("reasoning") or result.preview
            self.agent_state.record_step(
                type="tool",
                command=command,
                success=True,
                preview=reasoning or result.preview,
                result_key=result.raw_output_key,
                output=result.observation,
                is_summary=False,
                is_smart_summary=result.is_smart_summary,
            )
            return None

        if cmd_type == "sandbox":
            error_code = result.error_code or result.error
            if not result.success:
                result_key = result.raw_output_key
                self.agent_state.record_step(
                    type="sandbox",
                    command=command,
                    success=False,
                    preview=error_message,
                    result_key=result_key,
                    error=error_code,
                    output=observation,
                    is_summary=False,
                )
                if error_code == "sandbox_syntax_error":
                    prior_errors = observation.get("prior_errors", 0)
                    if prior_errors >= 2:
                        return self._failure(
                            error_code,
                            error_message,
                            preview=error_message,
                            recorded_step=True,
                        )
                    return None
                return self._failure(
                    error_code or "sandbox_runtime_error",
                    error_message,
                    preview=error_message,
                    recorded_step=True,
                )

            reasoning = command.get("reasoning") or result.preview
            self.agent_state.record_step(
                type="sandbox",
                command=command,
                success=True,
                preview=reasoning or result.preview,
                result_key=result.raw_output_key,
                output=result.observation,
                is_summary=False,
                is_smart_summary=result.is_smart_summary,
            )
            return None

        return None

    def _check_budget(self) -> MCPTaskResult | None:
        snapshot = self.agent_state.budget_tracker.snapshot()
        if snapshot.steps_taken >= snapshot.max_steps:
            return self._budget_failure("max_steps")
        if snapshot.tool_calls >= snapshot.max_tool_calls:
            return self._budget_failure("max_tool_calls")
        if snapshot.code_runs >= snapshot.max_code_runs:
            return self._budget_failure("max_code_runs")
        if snapshot.estimated_llm_cost_usd >= snapshot.max_llm_cost_usd:
            return self._budget_failure("max_llm_cost_usd")
        return None

    def _budget_failure(self, budget_type: str) -> MCPTaskResult:
        snapshot = self.agent_state.budget_tracker.snapshot()
        message = f"Budget exceeded: {budget_type}"
        payload = {
            "budget_type": budget_type,
            "cost": snapshot.estimated_llm_cost_usd,
            "steps_taken": snapshot.steps_taken,
        }
        model_name = getattr(self.llm, "model", None)
        if model_name:
            payload["model"] = model_name
        self.agent_state.record_event("mcp.budget.exceeded", payload)
        self.agent_state.record_step(
            type="finish",
            command={"type": "finish", "summary": message},
            success=False,
            preview=message,
            error=budget_type,
            output={"summary": message},
            is_summary=False,
        )
        # Use a stable, coarse-grained error_code while preserving the
        # budget_type detail in error_details.
        details = {
            "budget_type": budget_type,
            "snapshot": snapshot.to_dict(),
        }
        return self._failure("budget_exceeded", message, preview=message, recorded_step=True, details=details)

    def _success_result(self, summary: str) -> MCPTaskResult:
        """Build a terminal success result snapshot."""
        snapshot = self.agent_state.budget_tracker.snapshot()
        steps = [asdict(step) for step in self.agent_state.history]
        return MCPTaskResult(
            success=True,
            final_summary=summary,
            user_id=self.agent_state.user_id,
            run_id=self.agent_state.run_id,
            raw_outputs=self.agent_state.raw_outputs,
            budget_usage=snapshot.to_dict(),
            logs=self.agent_state.logs,
            steps=steps,
        )

    def _failure(
        self,
        reason: str,
        summary: str,
        preview: str | None = None,
        *,
        recorded_step: bool = False,
        details: Dict[str, Any] | None = None,
    ) -> MCPTaskResult:
        """
        Common helper to build a terminal failure result snapshot.

        `reason` is treated as the canonical error_code and is also exposed
        via the legacy `error` field for backwards compatibility.
        """
        snapshot = self.agent_state.budget_tracker.snapshot()
        self.agent_state.record_event(
            "mcp.planner.failed",
            {
                "reason": reason,
                "llm_preview": (preview or "")[:200],
            },
        )
        if not recorded_step:
            self.agent_state.record_step(
                type="finish",
                command={"type": "finish", "summary": summary},
                success=False,
                preview=summary,
                error=reason,
                output={"summary": summary},
                is_summary=False,
            )
        steps = [asdict(step) for step in self.agent_state.history]
        result: MCPTaskResult = MCPTaskResult(
            success=False,
            final_summary=summary,
            user_id=self.agent_state.user_id,
            run_id=self.agent_state.run_id,
            raw_outputs=self.agent_state.raw_outputs,
            budget_usage=snapshot.to_dict(),
            logs=self.agent_state.logs,
            error=reason,
            error_code=reason,
            error_message=summary,
            steps=steps,
        )
        if details is not None:
            result["error_details"] = details
        return result


# --- High-level entrypoint ---


def execute_mcp_task(
    task: str,
    *,
    user_id: str,
    budget: Budget | None = None,
    extra_context: Dict[str, Any] | None = None,
    llm: PlannerLLM | None = None,
) -> MCPTaskResult:
    """
    Execute a standalone MCP task and return a structured result.

    Args:
        task: Required natural-language request from the user.
        user_id: Required identifier used to scope MCP registry state.
        budget: Optional overrides for step/tool/code/cost ceilings.
        extra_context: Optional dict of metadata accessible to the planner.

    Returns:
        MCPTaskResult: structure containing success, summary, budget usage, logs, and optional error.
    """

    if not isinstance(task, str) or not task.strip():
        raise ValueError("task must be a non-empty string.")
    normalized_user = normalize_user_id(user_id)

    with tempfile.TemporaryDirectory(prefix=f"toolbox-{normalized_user}-") as temp_dir:
        toolbox_path = Path(temp_dir)

        agent_context = AgentContext.create(
            user_id=normalized_user,
            extra={"toolbox_root": str(toolbox_path)},
        )

        generate_ephemeral_toolbox(agent_context, toolbox_path)

        state = AgentState(
            task=task.strip(),
            user_id=normalized_user,
            request_id=agent_context.request_id,
            budget=budget or Budget(),
            extra_context=extra_context or {},
        )
        for provider in ("gmail", "slack"):
            ensure_env_for_provider(normalized_user, provider)
        state.record_event(
            "mcp.planner.started",
            {
                "budget": asdict(state.budget_tracker.snapshot()),
                "extra_context_keys": sorted(state.extra_context.keys()),
                "ephemeral_toolbox": str(toolbox_path),
            },
        )
        runtime = AgentOrchestrator(agent_context, state, llm=llm)
        return runtime.run()


# Backward compatibility alias
PlannerRuntime = AgentOrchestrator
