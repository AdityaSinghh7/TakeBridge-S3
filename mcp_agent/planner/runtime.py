from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, Optional, TypedDict

from .budget import Budget, BudgetSnapshot
from .context import PlannerContext
from .discovery import perform_initial_discovery, perform_refined_discovery
from .llm import PlannerLLM
from .parser import parse_planner_command
from .actions import call_direct_tool
from .sandbox import run_sandbox_plan


class MCPTaskResult(TypedDict, total=False):
    success: bool
    final_summary: str
    raw_outputs: Dict[str, Any]
    budget_usage: Dict[str, Any]
    logs: list[Dict[str, Any]]
    error: Optional[str]


class PlannerRuntime:
    """Placeholder runtime until the full planner loop is implemented."""

    def __init__(self, context: PlannerContext, llm: PlannerLLM | None = None) -> None:
        self.context = context
        self.llm = llm or PlannerLLM()

    def run(self) -> MCPTaskResult:
        perform_initial_discovery(self.context)
        while True:
            exceeded = self._budget_exceeded()
            if exceeded:
                return self._budget_failure(exceeded)

            self.context.budget_tracker.steps_taken += 1
            llm_result = self.llm.generate_plan(self.context)
            text = llm_result.get("text") or ""
            try:
                command = parse_planner_command(text)
            except ValueError as exc:
                return self._failure("planner_parse_error", str(exc), preview=text)

            cmd_type = command["type"]
            if cmd_type == "finish":
                summary = command.get("summary") or "Task completed."
                snapshot = self.context.budget_tracker.snapshot()
                self.context.record_event(
                    "mcp.planner.finished",
                    {"summary_preview": summary[:200]},
                )
                return MCPTaskResult(
                    success=True,
                    final_summary=summary,
                    raw_outputs=self.context.raw_outputs,
                    budget_usage=snapshot.to_dict(),
                    logs=self.context.logs,
                    error=None,
                )

            if cmd_type == "tool":
                result = self._execute_tool(command)
                if result is not None:
                    return result
                continue

            if cmd_type == "sandbox":
                result = self._execute_sandbox(command)
                if result is not None:
                    return result
                continue

            if cmd_type == "search":
                result = self._execute_search(command)
                if result is not None:
                    return result
                continue

            return self._failure("planner_unknown_command", "Unsupported planner command.", preview=text)

    def _budget_exceeded(self) -> str | None:
        snapshot = self.context.budget_tracker.snapshot()
        if snapshot.steps_taken >= snapshot.max_steps:
            return "max_steps"
        if snapshot.tool_calls >= snapshot.max_tool_calls:
            return "max_tool_calls"
        if snapshot.code_runs >= snapshot.max_code_runs:
            return "max_code_runs"
        if snapshot.estimated_llm_cost_usd >= snapshot.max_llm_cost_usd:
            return "max_llm_cost_usd"
        return None

    def _budget_failure(self, budget_type: str) -> MCPTaskResult:
        snapshot = self.context.budget_tracker.snapshot()
        message = f"Budget exceeded: {budget_type}"
        self.context.record_event(
            "mcp.budget.exceeded",
            {"budget_type": budget_type},
        )
        return MCPTaskResult(
            success=False,
            final_summary=message,
            raw_outputs=self.context.raw_outputs,
            budget_usage=snapshot.to_dict(),
            logs=self.context.logs,
            error="budget_exceeded",
        )

    def _failure(self, reason: str, summary: str, preview: str | None = None) -> MCPTaskResult:
        snapshot = self.context.budget_tracker.snapshot()
        self.context.record_event(
            "mcp.planner.failed",
            {
                "reason": reason,
                "llm_preview": (preview or "")[:200],
            },
        )
        return MCPTaskResult(
            success=False,
            final_summary=summary,
            raw_outputs=self.context.raw_outputs,
            budget_usage=snapshot.to_dict(),
            logs=self.context.logs,
            error=reason,
        )

    def _execute_tool(self, command: Dict[str, Any]) -> MCPTaskResult | None:
        provider = command.get("provider")
        tool = command.get("tool")
        payload = command.get("payload") or {}
        if not provider or not tool:
            return self._failure("tool_missing_fields", "Tool command missing provider/tool.", preview=str(command))
        self.context.record_event(
            "mcp.action.planned",
            {"provider": provider, "tool": tool},
        )
        try:
            call_direct_tool(self.context, provider=provider, tool=tool, payload=payload)
        except Exception as exc:
            return self._failure("tool_execution_failed", f"Tool execution failed: {exc}", preview=str(command))
        self.context.record_event(
            "mcp.action.completed",
            {"provider": provider, "tool": tool},
        )
        return None

    def _execute_sandbox(self, command: Dict[str, Any]) -> MCPTaskResult | None:
        code_body = command.get("code")
        if not code_body:
            return self._failure("sandbox_missing_code", "Sandbox command missing code body.", preview=str(command))
        label = (command.get("label") or "sandbox").strip() or "sandbox"
        execution = run_sandbox_plan(self.context, code_body, label=label)
        sandbox_result = execution.result
        if sandbox_result.success:
            return None
        return self._failure(
            "sandbox_execution_failed",
            sandbox_result.error or "Sandbox execution failed.",
            preview="\n".join(sandbox_result.logs)[-200:],
        )

    def _execute_search(self, command: Dict[str, Any]) -> MCPTaskResult | None:
        query = (command.get("query") or "").strip()
        if not query:
            return self._failure("search_missing_query", "Search command missing query.", preview=str(command))
        detail_level = command.get("detail_level") or "summary"
        try:
            limit_value = int(command.get("limit") or 10)
        except (TypeError, ValueError):
            limit_value = 10
        limit_value = max(1, min(limit_value, 50))
        perform_refined_discovery(
            self.context,
            query=query,
            detail_level=detail_level,
            limit=limit_value,
        )
        return None


def execute_mcp_task(
    task: str,
    user_id: str = "singleton",
    budget: Budget | None = None,
    extra_context: Dict[str, Any] | None = None,
    toolbox_root: Path | None = None,
    *,
    llm: PlannerLLM | None = None,
) -> MCPTaskResult:
    """
    Execute a standalone MCP task and return a structured result.

    Args:
        task: Required natural-language request from the user.
        user_id: Optional identifier used to scope MCP registry state.
        budget: Optional overrides for step/tool/code/cost ceilings.
        extra_context: Optional dict of metadata accessible to the planner.
        toolbox_root: Optional path to a generated toolbox (defaults to ./toolbox).

    Returns:
        MCPTaskResult: structure containing success, summary, budget usage, logs, and optional error.
    """

    if not isinstance(task, str) or not task.strip():
        raise ValueError("task must be a non-empty string.")
    normalized_user = (user_id or "singleton").strip() or "singleton"
    resolved_toolbox = Path(toolbox_root).resolve() if toolbox_root else Path("toolbox").resolve()
    context = PlannerContext(
        task=task.strip(),
        user_id=normalized_user,
        budget=budget or Budget(),
        extra_context=extra_context or {},
        toolbox_root=resolved_toolbox,
    )
    context.record_event(
        "mcp.planner.started",
        {
            "budget": asdict(context.budget_tracker.snapshot()),
            "extra_context_keys": sorted(context.extra_context.keys()),
        },
    )
    runtime = PlannerRuntime(context, llm=llm)
    result = runtime.run()
    snapshot = context.budget_tracker.snapshot().to_dict()
    final_summary = result.get("final_summary")
    success_flag = bool(result.get("success"))
    if not final_summary:
        final_summary = "Task completed." if success_flag else "Task failed."
    return MCPTaskResult(
        success=success_flag,
        final_summary=final_summary,
        raw_outputs=result.get("raw_outputs") or context.raw_outputs,
        budget_usage=result.get("budget_usage") or snapshot,
        logs=result.get("logs") or context.logs,
        error=result.get("error"),
    )
