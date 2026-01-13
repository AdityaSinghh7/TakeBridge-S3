from __future__ import annotations

import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, Optional

from mcp_agent.core.context import AgentContext
from mcp_agent.actions import SUPPORTED_PROVIDERS
from mcp_agent.env_sync import ensure_env_for_provider
from mcp_agent.registry.crud import get_available_providers
from mcp_agent.user_identity import normalize_user_id
from mcp_agent.sandbox.ephemeral import generate_ephemeral_toolbox
from mcp_agent.utils.event_logger import log_mcp_event
from shared import agent_signal
from shared.run_context import RUN_LOG_ID

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
        agent_signal.raise_if_exit_requested()
        agent_signal.wait_for_resume()
        failure = self._ensure_llm_enabled()
        if failure:
            return failure

        self._load_inventory()

        while True:
            agent_signal.raise_if_exit_requested()
            agent_signal.wait_for_resume()
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

        # Pass tool constraints to inventory view if available
        inventory = get_inventory_view(
            self.agent_context,
            tool_constraints=self.agent_state.tool_constraints,
        )
        providers = inventory.get("providers", []) if isinstance(inventory, dict) else inventory
        self.agent_state.provider_tree = providers
        self.agent_state.discovery_completed = True

    def _next_command(self) -> tuple[Dict[str, Any] | None, MCPTaskResult | None]:
        """
        Ask the LLM for the next planner command and parse it.

        Handles empty-response retries and performs limited recovery attempts for
        protocol/shape errors before returning a terminal failure.
        """
        max_parse_retries = 2
        attempt = 0
        last_error: Exception | None = None
        last_text = ""

        while attempt <= max_parse_retries:
            attempt += 1
            llm_result = self.llm.generate_plan(self.agent_state)
            text = llm_result.get("text") or ""
            if not text:
                self.agent_state.record_event(
                    "mcp.llm.retry_empty",
                    {"raw_output": text, "attempt": attempt},
                )
                llm_result = self.llm.generate_plan(self.agent_state)
                text = llm_result.get("text") or ""
            try:
                return parse_planner_command(text), None
            except ValueError as exc:
                last_error = exc
                last_text = text
                # Protocol/shape error in planner output.
                self.agent_state.record_event(
                    "mcp.planner.protocol_error",
                    {
                        "error": str(exc),
                        "raw_preview": self._clean_llm_preview(text, limit=200),
                    },
                )
                if attempt <= max_parse_retries:
                    self.agent_state.record_event(
                        "mcp.planner.retry_parse_error",
                        {
                            "attempt": attempt,
                            "max_retries": max_parse_retries,
                            "error": str(exc),
                        },
                    )
                    continue
                break

        clean_error = self._format_parse_error(last_error, attempt)
        result = self._failure(
            "planner_parse_error",
            clean_error,
            preview=self._clean_llm_preview(last_text),
        )
        return None, result

    @staticmethod
    def _clean_llm_preview(text: str, limit: int = 400) -> str:
        if not text:
            return ""
        cleaned = "".join(ch if ch.isprintable() else " " for ch in text).strip()
        if len(cleaned) > limit:
            return cleaned[: max(0, limit - 3)] + "..."
        return cleaned

    @staticmethod
    def _format_parse_error(exc: Exception | None, attempts: int) -> str:
        base = str(exc).strip() if exc else "Planner response invalid."
        return f"{base} (parse retries exhausted after {attempts} attempts)."

    def _dispatch_command(self, command: Dict[str, Any]) -> MCPTaskResult | None:
        """
        Route a parsed planner command to the appropriate execution path.

        Returns a terminal MCPTaskResult when the planner should stop, or None
        when the loop should continue.
        """
        cmd_type = command["type"]
        if cmd_type in {"search", "tool", "sandbox", "inspect_tool_output"}:
            result = self._executor.execute_step(command)
            return self._handle_action_result(command, result)

        if cmd_type == "finish":
            self._executor.execute_step(command)
            summary = command.get("summary") or "Task completed."
            reasoning = command.get("reasoning") or ""
            data = command.get("data")
            action_input = {"summary": summary, "reasoning": reasoning}
            action_outcome = {"success": True, "final_summary": summary}
            if data is not None:
                action_input["data"] = data
                action_outcome["data"] = data
            self.agent_state.record_step(
                action_type="finish",
                success=True,
                action_reasoning=reasoning,
                action_input=action_input,
                action_outcome=action_outcome,
                observation=None,
                observation_metadata=None,
                error=None,
            )
            return self._success_result(summary)

        if cmd_type == "fail":
            self._executor.execute_step(command)
            reason_text = command.get("reason") or "Planner reported a failure."
            reasoning = command.get("reasoning") or ""
            self.agent_state.record_step(
                action_type="fail",
                success=False,
                action_reasoning=reasoning,
                action_input={"reason": reason_text, "reasoning": reasoning},
                action_outcome={"success": False, "error": reason_text},
                observation=None,
                observation_metadata=None,
                error=reason_text,
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
                self.agent_state.record_step(
                    action_type="search",
                    success=False,
                    action_reasoning=command.get("reasoning") or "",
                    action_input={
                        "search_query": (command.get("query") or "").strip(),
                        "provider": command.get("provider") or command.get("server"),
                        "max_limit": command.get("limit") or command.get("max_results"),
                        "reasoning": command.get("reasoning") or "",
                    },
                    action_outcome={"success": False, "error": error_message},
                    observation={"error": error_message, "found_tools": []},
                    observation_metadata={
                        "total_found": 0,
                    },
                    error=result.error_code or error_message,
                )
                return self._failure(result.error_code or "search_failed", error_message, preview=str(command))
            query = (command.get("query") or "").strip()
            found_tools = observation.get("found_tools", [])
            tool_names = [
                (t.get("tool") or t.get("tool_id") or "").strip()
                for t in found_tools
                if isinstance(t, dict)
            ]
            self.agent_state.merge_search_results(found_tools, replace=False)
            # found_tools are already compact - no need to slim further
            self.agent_state.record_event(
                "mcp.search.completed",
                {
                    "query": query,
                    "detail_level": "full",
                    "result_count": len(found_tools),
                    "tool_ids": [r.get("tool_id") for r in found_tools if r.get("tool_id")],
                    "tool_names": tool_names,
                },
            )
            reasoning = command.get("reasoning") or result.preview
            self.agent_state.record_step(
                action_type="search",
                success=True,
                action_reasoning=reasoning,
                action_input={
                    "search_query": query,
                    "provider": command.get("provider") or command.get("server"),
                    "max_limit": command.get("limit") or command.get("max_results"),
                    "reasoning": reasoning,
                },
                action_outcome={
                    "success": True,
                    "total_found": len(found_tools),
                    "found_tool_names": tool_names,
                },
                observation=(
                    f"Search succeeded; found {len(found_tools)} tools: "
                    f"{', '.join([name for name in tool_names if name]) or 'none'}. "
                    "Details merged into available_tools."
                ),
                # Minimal metadata for trajectory consumption
                observation_metadata={
                    "total_found": len(found_tools),
                    "merged_into_cache": True,
                    "cache_size_after": len(self.agent_state.search_results),
                },
            )
            return None

        if cmd_type == "inspect_tool_output":
            tool_id = (command.get("tool_id") or "").strip()
            field_path = (command.get("field_path") or "").strip()
            max_depth = command.get("max_depth", 4)
            max_fields = command.get("max_fields", 120)
            reasoning = command.get("reasoning") or result.preview

            if not result.success:
                # Inspect is non-terminal: return the error to the planner so it can retry.
                self.agent_state.record_step(
                    action_type="inspect_tool_output",
                    success=False,
                    action_reasoning=reasoning,
                    action_input={
                        "tool_id": tool_id,
                        "field_path": field_path,
                        "max_depth": max_depth,
                        "max_fields": max_fields,
                        "reasoning": reasoning,
                    },
                    action_outcome={"success": False, "error": error_message},
                    observation=result.observation if result.observation else {"error": error_message},
                    observation_metadata={
                        "is_smart_summary": result.is_smart_summary,
                    },
                    error=result.error_code or result.error or "inspect_tool_output_failed",
                )
                return None

            outcome: Dict[str, Any] = {"success": True}
            obs = result.observation
            if isinstance(obs, dict):
                if "truncated" in obs:
                    outcome["truncated"] = obs.get("truncated")
                if "total_child_fields" in obs:
                    outcome["total_child_fields"] = obs.get("total_child_fields")

            self.agent_state.record_step(
                action_type="inspect_tool_output",
                success=True,
                action_reasoning=reasoning,
                action_input={
                    "tool_id": tool_id,
                    "field_path": field_path,
                    "max_depth": max_depth,
                    "max_fields": max_fields,
                    "reasoning": reasoning,
                },
                action_outcome=outcome,
                observation=obs,
                observation_metadata={
                    "is_smart_summary": result.is_smart_summary,
                },
                error=None,
                is_smart_summary=result.is_smart_summary,
            )
            return None

        if cmd_type == "tool":
            resolved_tool_id = result.tool_id or command.get("tool_id") or f"{command.get('provider')}.{command.get('tool')}"
            resolved_provider = result.provider or result.server or command.get("provider") or command.get("server")
            resolved_tool = result.tool_name or command.get("tool") or (
                resolved_tool_id.split(".", 1)[1] if resolved_tool_id and "." in resolved_tool_id else command.get("tool")
            )
            resolved_args = result.args if result.args is not None else (command.get("args") or command.get("payload") or {})
            resolved_action_input = {
                "tool_id": resolved_tool_id,
                "provider": resolved_provider,
                "tool": resolved_tool,
                "args": resolved_args,
            }

            if not result.success:
                self.agent_state.record_step(
                    action_type="tool",
                    success=False,
                    action_reasoning=command.get("reasoning") or "",
                    action_input=resolved_action_input,
                    action_outcome={
                        "success": False,
                        "error": error_message,
                    },
                    observation=result.observation if result.observation else {"error": error_message},
                    error=result.error_code or result.error or "tool_execution_failed",
                )
                return self._failure(
                    result.error_code or "tool_execution_failed",
                    error_message,
                    preview=str(command),
                    recorded_step=True,
                )
            reasoning = command.get("reasoning") or result.preview
            self.agent_state.record_step(
                action_type="tool",
                success=True,
                action_reasoning=reasoning,
                action_input=resolved_action_input,
                action_outcome={
                    "success": True,
                },
                observation=result.observation,
                observation_metadata={
                    "is_smart_summary": result.is_smart_summary,
                },
                error=None,
            )
            return None

        if cmd_type == "sandbox":
            error_code = result.error_code or result.error
            if not result.success:
                self.agent_state.record_step(
                    action_type="sandbox",
                    success=False,
                    action_reasoning=command.get("reasoning") or "",
                    action_input={
                        "sandbox_code": command.get("code"),
                        "label": command.get("label"),
                    },
                    action_outcome={
                        "success": False,
                        "error": error_message,
                    },
                    observation=result.observation if result.observation else observation,
                    observation_metadata={
                        "retry_count": observation.get("prior_errors", 0) if isinstance(observation, dict) else 0,
                    },
                    error=error_code,
                )
                recoverable_codes = {
                    "sandbox_syntax_error",
                    "sandbox_logic_error",
                    "sandbox_invalid_body",
                    "sandbox_empty_result",
                    "sandbox_runtime_error",
                }
                if error_code in recoverable_codes:
                    prior_errors = observation.get("prior_errors", 0) if isinstance(observation, dict) else 0
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
            all_tools_succeeded = bool(
                isinstance(observation, dict) and observation.get("_all_tools_succeeded")
            )
            action_outcome_success = (
                all_tools_succeeded
                if isinstance(observation, dict) and "_all_tools_succeeded" in observation
                else True
            )
            self.agent_state.record_step(
                action_type="sandbox",
                success=True,
                action_reasoning=reasoning,
                action_input={
                    "sandbox_code": command.get("code"),
                    "label": command.get("label"),
                },
                action_outcome={
                    "success": action_outcome_success,
                    "all_tools_successfully_returned": all_tools_succeeded,
                },
                observation=result.observation,
                observation_metadata={
                    "is_smart_summary": result.is_smart_summary,
                },
                error=None,
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
            action_type="finish",
            success=False,
            action_reasoning="budget_exceeded",
            action_input={"summary": message},
            action_outcome={"success": False, "error": message, "budget_type": budget_type},
            error=budget_type,
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
        steps = [step.to_dict() for step in self.agent_state.history]

        # Generate rich markdown trajectory for orchestrator
        trajectory_md = self.agent_state.build_markdown_trajectory()

        return MCPTaskResult(
            success=True,
            final_summary=summary,
            user_id=self.agent_state.user_id,
            run_id=self.agent_state.run_id,
            raw_outputs=self.agent_state.raw_outputs,
            budget_usage=snapshot.to_dict(),
            logs=self.agent_state.logs,
            steps=steps,
            trajectory_md=trajectory_md,
            state_dict=self.agent_state.to_dict(),
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
                action_type="finish",
                success=False,
                action_reasoning="planner_failure",
                action_input={"summary": summary},
                action_outcome={"success": False, "error": summary},
                observation=None,
                observation_metadata=None,
                error=reason,
            )
        steps = [step.to_dict() for step in self.agent_state.history]

        # Generate rich markdown trajectory for orchestrator
        trajectory_md = self.agent_state.build_markdown_trajectory()

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
            trajectory_md=trajectory_md,
            state_dict=self.agent_state.to_dict(),
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
            - tool_constraints: Optional dict with mode/providers/tools
            - step_id: Optional step identifier for hierarchical logging

    Returns:
        MCPTaskResult: structure containing success, summary, budget usage, logs, and optional error.
    """
    from shared.streaming import emit_event
    from shared.hierarchical_logger import (
        get_hierarchical_logger,
        set_hierarchical_logger,
        set_step_id,
        HierarchicalLogger,
    )

    if not isinstance(task, str) or not task.strip():
        raise ValueError("task must be a non-empty string.")
    normalized_user = normalize_user_id(user_id)

    # Extract tool constraints from extra_context
    extra_context = extra_context or {}
    tool_constraints = extra_context.get("tool_constraints")
    step_id = extra_context.get("step_id", "mcp-main")
    # Bind run_id to context for per-run logging when present
    run_token = None
    run_id = extra_context.get("request_id") or extra_context.get("run_id")
    if run_id:
        run_token = RUN_LOG_ID.set(run_id)

    try:
        # Get or create hierarchical logger
        h_logger = get_hierarchical_logger()
        if not h_logger:
            # Standalone execution (not via orchestrator)
            h_logger = HierarchicalLogger(task)
            set_hierarchical_logger(h_logger)

        # Bind step_id to context
        set_step_id(step_id)

        # Get agent logger
        mcp_logger = h_logger.get_agent_logger("mcp", step_id)

        # Emit SSE event: task started
        started_payload = {
            "task": task,
            "user_id": normalized_user,
            "step_id": step_id,
            "tool_constraints": tool_constraints,
        }
        emit_event("mcp.task.started", started_payload)
        log_mcp_event("mcp.task.started", started_payload, source="run_loop")

        # Log to hierarchical logger
        mcp_logger.log_event("task.started", {
            "task": task,
            "user_id": normalized_user,
            "tool_constraints": tool_constraints,
        })

        with tempfile.TemporaryDirectory(prefix=f"toolbox-{normalized_user}-") as temp_dir:
            toolbox_path = Path(temp_dir)

            agent_context = AgentContext.create(
                user_id=normalized_user,
                extra={"toolbox_root": str(toolbox_path)},
            )

            generate_ephemeral_toolbox(agent_context, toolbox_path)

            provider_infos = get_available_providers(agent_context)
            available_providers = [
                info.get("provider")
                for info in provider_infos
                if info.get("authorized") and info.get("provider")
            ]
            if tool_constraints and tool_constraints.get("mode") == "custom":
                allowed_providers = tool_constraints.get("providers") or []
                allowed_tools = tool_constraints.get("tools") or []
                if allowed_providers:
                    allowed_provider_set = set(allowed_providers)
                    available_providers = [
                        provider
                        for provider in available_providers
                        if provider in allowed_provider_set
                    ]
                if allowed_tools:
                    tool_provider_set = {
                        tool.split(".", 1)[0]
                        for tool in allowed_tools
                        if isinstance(tool, str) and tool
                    }
                    if tool_provider_set:
                        available_providers = [
                            provider
                            for provider in available_providers
                            if provider in tool_provider_set
                        ]

            state = AgentState(
                task=task.strip(),
                user_id=normalized_user,
                request_id=agent_context.request_id,
                budget=budget or Budget(),
                extra_context=extra_context,
                tool_constraints=tool_constraints,  # NEW: Set tool constraints on state
            )
            for provider in SUPPORTED_PROVIDERS:
                ensure_env_for_provider(normalized_user, provider)
            state.record_event(
                "mcp.planner.started",
                {
                    "budget": asdict(state.budget_tracker.snapshot()),
                    "extra_context_keys": sorted(state.extra_context.keys()),
                    "ephemeral_toolbox": str(toolbox_path),
                    "tool_constraints": tool_constraints,
                    "available_providers": available_providers,
                },
            )
            runtime = AgentOrchestrator(agent_context, state, llm=llm)
            result = runtime.run()

            # Emit SSE event: task completed
            completed_payload = {
                "success": result.get("success", False),
                "step_id": step_id,
            }
            emit_event("mcp.task.completed", completed_payload)
            log_mcp_event("mcp.task.completed", completed_payload, source="run_loop")

            # Log to hierarchical logger
            mcp_logger.log_event("task.completed", {
                "success": result.get("success", False),
                "error": result.get("error") if not result.get("success", False) else None,
            })

            return result
    finally:
        if run_token:
            RUN_LOG_ID.reset(run_token)


# Backward compatibility alias
PlannerRuntime = AgentOrchestrator
