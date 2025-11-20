from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, Optional, TypedDict
import traceback
import ast
import json

from mcp_agent.user_identity import normalize_user_id
from mcp_agent.env_sync import ensure_env_for_provider
from mcp_agent.knowledge.builder import get_index

from .budget import Budget, BudgetSnapshot
from .context import PlannerContext, _slim_tool_for_planner
from .discovery import load_provider_topology, perform_refined_discovery
from .llm import PlannerLLM
from .parser import parse_planner_command
from .sandbox_runner import run_sandbox_plan
from .summarize import summarize_payload

# Import for new architecture: routing through Python wrappers
from mcp_agent.actions import get_provider_action_map
from mcp_agent.actions.dispatcher import dispatch_tool
from mcp_agent.core.context import AgentContext


# Planner result contract returned from execute_mcp_task and PlannerRuntime.run.
# Fields:
#   - success: overall success flag for the task.
#   - final_summary: human-readable summary of what happened.
#   - error / error_code / error_message / error_details: failure information
#     (error is kept as a legacy alias for error_code to preserve existing APIs).
#   - user_id / run_id: identifiers for the logical user and this planner run.
#   - budget_usage: serialized BudgetSnapshot for this run.
#   - logs: planner event log entries.
#   - raw_outputs: per-key raw tool/sandbox outputs recorded during the run.
#   - steps: serialized PlannerStep history.
class MCPTaskResult(TypedDict, total=False):
    success: bool
    final_summary: str
    error: Optional[str]
    error_code: Optional[str]
    error_message: Optional[str]
    error_details: Dict[str, Any]
    user_id: str
    run_id: str
    raw_outputs: Dict[str, Any]
    budget_usage: Dict[str, Any]
    logs: list[Dict[str, Any]]
    steps: list[Dict[str, Any]]


class _PlannerAbort(Exception):
    """Internal control-flow exception used to exit the planner loop early."""

    def __init__(self, result: MCPTaskResult) -> None:
        self.result = result


def analyze_sandbox(code: str) -> tuple[set[str], Dict[str, set[str]]]:
    """
    Analyze sandbox code to extract imported servers and function calls.

    Returns:
        used_servers: set of server names referenced via sandbox_py.servers imports.
        calls_by_server: mapping server -> set of function names called on that server.
    """

    used_servers: set[str] = set()
    calls_by_server: Dict[str, set[str]] = {}

    class SandboxVisitor(ast.NodeVisitor):
        def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
            # from sandbox_py.servers import gmail
            if node.module == "sandbox_py.servers":
                for alias in node.names:
                    used_servers.add(alias.name)
            self.generic_visit(node)

        def visit_Import(self, node: ast.Import) -> None:
            # import sandbox_py.servers.gmail as gmail
            for alias in node.names:
                if alias.name.startswith("sandbox_py.servers."):
                    server = alias.name.split(".")[-1]
                    used_servers.add(server)
            self.generic_visit(node)

        def visit_Call(self, node: ast.Call) -> None:
            # gmail.gmail_search(...)
            func = node.func
            if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
                server = func.value.id
                func_name = func.attr
                calls_by_server.setdefault(server, set()).add(func_name)
            self.generic_visit(node)

    tree = ast.parse(code)
    SandboxVisitor().visit(tree)
    return used_servers, calls_by_server


def _smart_format_observation(payload: Any, max_chars: int = 15000) -> Any:
    """
    Return raw data if it fits in context, otherwise summarize.
    
    This allows the model to see actual data for small payloads (e.g., a few emails)
    while automatically summarizing large payloads (e.g., 100 emails).
    
    Args:
        payload: The data to format (may be an MCP envelope or raw data)
        max_chars: Maximum character length before summarization triggers
    
    Returns:
        Either the raw data (if small enough) or a summary dict
    """
    # 1. Unwrap MCP envelope if present
    data = payload
    if isinstance(payload, dict):
        if "successful" in payload:
            # This is an MCP envelope
            if not payload["successful"]:
                # Return error immediately for failed calls
                return {"error": payload.get("error", "Unknown failure")}
            # Extract the data field
            data = payload.get("data", {})
    
    # 2. Check size of the data
    try:
        text = json.dumps(data, default=str, ensure_ascii=False)
        if len(text) <= max_chars:
            # Small enough - return raw data
            return data
    except Exception:
        # If serialization fails, fall through to summary
        pass
    
    # 3. Too large - return summary
    return summarize_payload("tool_output", data, purpose="planner_observation")


class PlannerRuntime:
    """Coordinator for the high-level planner loop."""

    def __init__(self, context: PlannerContext, llm: PlannerLLM | None = None) -> None:
        self.context = context
        self.llm = llm or PlannerLLM()
        self._executor = None  # Lazy-initialized ActionExecutor

    def _get_executor(self):
        """Get or create ActionExecutor for new architecture paths.

        This lazily creates an ActionExecutor and AgentContext when needed,
        providing a bridge between the legacy PlannerContext and new architecture.
        """
        if self._executor is None:
            from mcp_agent.core.context import AgentContext
            from .executor import ActionExecutor
            from .state import AgentState

            # Create AgentContext from PlannerContext data
            agent_context = AgentContext.create(user_id=self.context.user_id)

            # Create AgentState (minimal bridge - we'll sync back to PlannerContext)
            agent_state = AgentState(
                task=self.context.task,
                user_id=self.context.user_id,
                request_id=self.context.run_id,
                budget=self.context.budget,
            )

            # Create executor
            self._executor = ActionExecutor(agent_context, agent_state)

        return self._executor

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
        try:
            self._ensure_llm_enabled()
        except _PlannerAbort as exc:
            return exc.result
        load_provider_topology(self.context)
        while True:
            exceeded = self._budget_exceeded()
            if exceeded:
                return self._budget_failure(exceeded)

            self.context.budget_tracker.steps_taken += 1
            try:
                command = self._next_command()
            except _PlannerAbort as exc:
                return exc.result

            result = self._dispatch_command(command)
            if result is not None:
                return result

    def _ensure_llm_enabled(self) -> None:
        """Verify that the planner LLM is enabled before starting the loop."""
        llm_enabled = True
        is_enabled = getattr(self.llm, "is_enabled", None)
        if callable(is_enabled):
            try:
                llm_enabled = bool(is_enabled())
            except Exception:
                llm_enabled = True
        if not llm_enabled:
            result = self._failure("planner_llm_disabled", "Planner LLM is disabled.")
            raise _PlannerAbort(result)

    def _next_command(self) -> Dict[str, Any]:
        """
        Ask the LLM for the next planner command and parse it.

        Handles empty-response retries and converts protocol/shape errors into a
        terminal planner failure.
        """
        llm_result = self.llm.generate_plan(self.context)
        text = llm_result.get("text") or ""
        if not text:
            self.context.record_event(
                "mcp.llm.retry_empty",
                {"model": self.llm.model},
            )
            llm_result = self.llm.generate_plan(self.context)
            text = llm_result.get("text") or ""
        try:
            return parse_planner_command(text)
        except ValueError as exc:
            # Protocol/shape error in planner output.
            self.context.record_event(
                "mcp.planner.protocol_error",
                {
                    "error": str(exc),
                    "raw_preview": text[:200],
                },
            )
            result = self._failure("planner_parse_error", str(exc), preview=text)
            raise _PlannerAbort(result)

    def _dispatch_command(self, command: Dict[str, Any]) -> MCPTaskResult | None:
        """
        Route a parsed planner command to the appropriate execution path.

        Returns a terminal MCPTaskResult when the planner should stop, or None
        when the loop should continue.
        """
        cmd_type = command["type"]
        if cmd_type == "finish":
            summary = command.get("summary") or "Task completed."
            reasoning = command.get("reasoning") or ""
            self.context.record_event(
                "mcp.planner.finished",
                {"summary_preview": summary[:200]},
            )
            self.context.record_step(
                type="finish",
                command=command,
                success=True,
                preview=reasoning or summary,
                output={"summary": summary},
                is_summary=False,
            )
            return self._success_result(summary)

        if cmd_type == "fail":
            reason_text = command.get("reason") or "Planner reported a failure."
            # Treat planner-declared fail as a clean, explicit failure.
            return self._failure("planner_fail_action", reason_text, preview=str(command))

        if cmd_type == "tool":
            return self._execute_tool(command)

        if cmd_type == "sandbox":
            return self._execute_sandbox(command)

        if cmd_type == "search":
            return self._execute_search(command)

        # Unknown or unsupported command type.
        return self._failure(
            "planner_unknown_command",
            "Unsupported planner command.",
            preview=str(command),
        )

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
        payload = {
            "budget_type": budget_type,
            "cost": snapshot.estimated_llm_cost_usd,
            "steps_taken": snapshot.steps_taken,
        }
        model_name = getattr(self.llm, "model", None)
        if model_name:
            payload["model"] = model_name
        self.context.record_event("mcp.budget.exceeded", payload)
        self.context.record_step(
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
        snapshot = self.context.budget_tracker.snapshot()
        steps = [asdict(step) for step in self.context.steps]
        return MCPTaskResult(
            success=True,
            final_summary=summary,
            user_id=self.context.user_id,
            run_id=self.context.run_id,
            raw_outputs=self.context.raw_outputs,
            budget_usage=snapshot.to_dict(),
            logs=self.context.logs,
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
        snapshot = self.context.budget_tracker.snapshot()
        self.context.record_event(
            "mcp.planner.failed",
            {
                "reason": reason,
                "llm_preview": (preview or "")[:200],
            },
        )
        if not recorded_step:
            self.context.record_step(
                type="finish",
                command={"type": "finish", "summary": summary},
                success=False,
                preview=summary,
                error=reason,
                output={"summary": summary},
                is_summary=False,
            )
        steps = [asdict(step) for step in self.context.steps]
        result: MCPTaskResult = MCPTaskResult(
            success=False,
            final_summary=summary,
            user_id=self.context.user_id,
            run_id=self.context.run_id,
            raw_outputs=self.context.raw_outputs,
            budget_usage=snapshot.to_dict(),
            logs=self.context.logs,
            error=reason,
            error_code=reason,
            error_message=summary,
            steps=steps,
        )
        if details is not None:
            result["error_details"] = details
        return result

    def _search_stats(self) -> tuple[int, int]:
        """Return (total_search_steps, search_steps_with_results)."""
        total = 0
        non_empty = 0
        for step in self.context.steps:
            if step.type != "search":
                continue
            total += 1
            if isinstance(step.output, list) and step.output:
                non_empty += 1
        return total, non_empty

    def _validation_failure(
        self,
        base_reason: str,
        summary: str,
        command: Dict[str, Any],
    ) -> MCPTaskResult:
        """Common handler for planner validation errors with discovery-awareness."""
        self.context.record_event(
            "mcp.planner.validation_error",
            {
                "reason": base_reason,
                "command_preview": str(command)[:200],
            },
        )
        total_search, non_empty = self._search_stats()
        if (
            base_reason
            in {
                "planner_used_unknown_tool",
                "planner_used_undiscovered_tool",
                "planner_used_unknown_server",
            }
            and total_search >= 2
            and non_empty == 0
        ):
            return self._failure(
                "discovery_failed",
                "No suitable tools were found via search, so this environment cannot complete the requested task.",
                preview=str(command),
            )
        return self._failure(base_reason, summary, preview=str(command))

    def _execute_tool(self, command: Dict[str, Any]) -> MCPTaskResult | None:
        # Normalize command into (tool_id, server, args)
        tool_id = command.get("tool_id")
        server = command.get("server")
        args = command.get("args")

        provider = command.get("provider")
        tool_name = command.get("tool")
        payload = command.get("payload")

        if tool_id and server:
            if args is None:
                args = {}
            if not isinstance(args, dict):
                return self._validation_failure(
                    "tool_invalid_args",
                    "Tool command 'args' must be an object.",
                    command,
                )
        else:
            # Legacy shape (provider + tool + payload) kept for compatibility.
            if not provider or not tool_name:
                return self._failure(
                    "tool_missing_fields",
                    "Tool command missing provider/tool.",
                    preview=str(command),
                )
            if payload is None:
                payload = {}
            if not isinstance(payload, dict):
                return self._validation_failure(
                    "tool_invalid_payload",
                    "Tool command 'payload' must be an object.",
                    command,
                )
            tool_id = f"{provider}.{tool_name}"
            server = provider
            args = payload

        # Validate against ToolboxIndex
        index = get_index(self.context.user_id)
        spec = index.get_tool(tool_id)
        if spec is None:
            return self._validation_failure(
                "planner_used_unknown_tool",
                f"Planner requested unknown tool_id '{tool_id}'.",
                command,
            )

        discovered_tool_ids = {
            entry.get("tool_id")
            for entry in self.context.search_results
            if entry.get("tool_id")
        }
        has_search_steps = any(step.type == "search" for step in self.context.steps)
        if has_search_steps and tool_id not in discovered_tool_ids:
            return self._validation_failure(
                "planner_used_undiscovered_tool",
                f"Planner requested tool_id '{tool_id}' which was never discovered via search.",
                command,
            )

        provider = spec.provider
        tool_name = spec.name
        payload = args or {}
        resolved_tool = self.context.resolve_mcp_tool_name(provider, tool_name)
        command = dict(command)
        command.setdefault("provider", provider)
        command.setdefault("tool", tool_name)
        command.setdefault("resolved_tool", resolved_tool)
        self.context.record_event(
            "mcp.action.planned",
            {"provider": provider, "tool": resolved_tool},
        )
        result_key = f"tool.{provider}.{resolved_tool}"

        # Route through new dispatcher architecture
        try:
            # Create AgentContext from PlannerContext
            agent_context = AgentContext.create(user_id=self.context.user_id)

            # Remove 'context' from payload if present (it's now passed as first arg)
            clean_payload = {k: v for k, v in payload.items() if k != "context"}

            # Dispatch through the new architecture (automatically finds wrapper or raises ToolNotFoundError)
            response = dispatch_tool(
                context=agent_context,
                provider=provider,
                tool=tool_name,
                payload=clean_payload
            )
        except Exception as exc:
            error_message = str(exc)
            trace = "".join(traceback.format_exception(exc))
            self.context.record_event(
                "mcp.action.exception",
                {
                    "provider": provider,
                    "tool": resolved_tool,
                    "error": error_message,
                    "traceback": trace[-2000:],
                },
            )
            self.context.record_step(
                type="tool",
                command=command,
                success=False,
                preview=f"{provider}.{resolved_tool} failed: {error_message}",
                result_key=result_key,
                error=error_message,
                output={"error": error_message},
                is_summary=False,
            )
            return self._failure(
                "tool_execution_failed",
                f"Tool execution failed: {exc}",
                preview=str(command),
                recorded_step=True,
            )
        
        # Track tool call in budget
        self.context.budget_tracker.tool_calls += 1

        # Use smart observation formatting - show raw data if it fits, summary if too large
        observation = _smart_format_observation(response)

        response_success = True
        if isinstance(response, dict):
            response_success = response.get("successful", True)
        reasoning = command.get("reasoning") or ""
        self.context.record_step(
            type="tool",
            command=command,
            success=True,
            preview=reasoning or f"{provider}.{resolved_tool} (successful={response_success})",
            result_key=result_key,
            output=observation,
            is_summary=False,
        )
        self.context.record_event(
            "mcp.action.completed",
            {"provider": provider, "tool": resolved_tool},
        )
        return None

    def _execute_sandbox(self, command: Dict[str, Any]) -> MCPTaskResult | None:
        code_body = command.get("code")
        if not code_body:
            return self._failure("sandbox_missing_code", "Sandbox command missing code body.", preview=str(command))
        try:
            # Static validation: ensure sandbox code only references discovered helpers.
            used_servers, calls_by_server = analyze_sandbox(code_body)
        except SyntaxError as exc:
            label = (command.get("label") or "sandbox").strip() or "sandbox"
            error_text = f"Sandbox code has invalid syntax: {exc}"
            self.context.record_event(
                "mcp.sandbox.syntax_error",
                {
                    "label": label,
                    "error": str(exc),
                    "code_preview": code_body[:4000],
                },
            )
            # Count prior syntax errors for this label.
            prior_errors = 0
            for step in self.context.steps:
                if (
                    step.type == "sandbox"
                    and step.error == "sandbox_syntax_error"
                    and (step.command.get("label") or "").strip() == label
                ):
                    prior_errors += 1
            result_key = f"sandbox.{label}"
            # Record this sandbox step as a failed attempt.
            self.context.record_step(
                type="sandbox",
                command=command,
                success=False,
                preview=error_text,
                result_key=result_key,
                error="sandbox_syntax_error",
                output={"error": f"syntax_error: {exc}"},
                is_summary=False,
            )

            # After a few repeated syntax failures for the same label, escalate
            # to a hard planner failure to avoid infinite loops.
            if prior_errors >= 2:
                return self._failure(
                    "sandbox_syntax_error",
                    "Planner repeatedly produced invalid sandbox code; giving up.",
                    preview=error_text,
                    recorded_step=True,
                )
            # Otherwise, treat this as a step-level failure and allow the
            # planner to continue (e.g., retry with a simpler plan or fail).
            return None

        allowed_servers = {
            (entry.get("server") or entry.get("provider"))
            for entry in self.context.search_results
            if entry.get("server") or entry.get("provider")
        }
        allowed_py_names_by_server: Dict[str, set[str]] = {}
        for entry in self.context.search_results:
            server = (entry.get("server") or entry.get("provider"))
            py_name = entry.get("py_name") or entry.get("tool")
            if server and py_name:
                allowed_py_names_by_server.setdefault(server, set()).add(py_name)

        for server in used_servers:
            if server not in allowed_servers:
                return self._validation_failure(
                    "planner_used_unknown_server",
                    f"Sandbox used server '{server}' which was never discovered via search.",
                    command,
                )

        for server, funcs in calls_by_server.items():
            # Only enforce function-level checks for servers that correspond to
            # discovered sandbox helpers. Local variables like `res.get(...)`
            # are ignored here.
            if server not in allowed_py_names_by_server:
                continue
            allowed_funcs = allowed_py_names_by_server.get(server, set())
            for func in funcs:
                if func not in allowed_funcs:
                    return self._validation_failure(
                        "planner_used_undiscovered_tool",
                        f"Sandbox used '{server}.{func}' which was not in search results.",
                        command,
                    )

        label = (command.get("label") or "sandbox").strip() or "sandbox"

        execution = run_sandbox_plan(self.context, code_body, label=label)
        sandbox_result = execution.result
        result_key = f"sandbox.{label}"

        # Track sandbox execution in budget
        self.context.budget_tracker.code_runs += 1

        if sandbox_result.success:
            # Use smart observation formatting - show raw result if it fits, summary if too large
            observation = _smart_format_observation(sandbox_result.result)
            reasoning = command.get("reasoning") or ""
            self.context.record_step(
                type="sandbox",
                command=command,
                success=True,
                preview=reasoning or f"Sandbox '{label}' success",
                result_key=result_key,
                output=observation,
                is_summary=False,
            )
            return None
        
        # Failure case - format the error observation
        error_payload = {
            "error": sandbox_result.error or "sandbox_execution_failed",
        }
        observation = _smart_format_observation(error_payload)
        reasoning = command.get("reasoning") or ""
        self.context.record_step(
            type="sandbox",
            command=command,
            success=False,
            preview=reasoning or f"Sandbox '{label}' failed",
            result_key=result_key,
            error=sandbox_result.error or "sandbox_execution_failed",
            output=observation,
            is_summary=False,
        )
        return self._failure(
            "sandbox_runtime_error",
            sandbox_result.error or "Sandbox execution failed.",
            preview="\n".join(sandbox_result.logs)[-200:],
            recorded_step=True,
        )

    def _execute_search(self, command: Dict[str, Any]) -> MCPTaskResult | None:
        """Execute search command using ActionExecutor."""
        query = (command.get("query") or "").strip()
        if not query:
            return self._failure("search_missing_query", "Search command missing query.", preview=str(command))

        # Use ActionExecutor for new architecture
        executor = self._get_executor()
        observation = executor.execute_action(
            action_type="search",
            action_input={"query": query, "provider": command.get("provider")}
        )

        # Sync budget tracking back to PlannerContext
        self.context.budget_tracker.steps = executor.agent_state.budget_tracker.steps

        if not observation["success"]:
            return self._failure(
                "search_failed",
                observation.get("error", "Search failed"),
                preview=str(command)
            )

        # Extract results from observation
        data = observation.get("data", {})
        found_tools = data.get("found_tools", [])

        # Sync discovered tools back to PlannerContext for backward compatibility
        self.context.merge_search_results(found_tools, replace=False)

        # Slim the results for the trajectory observation
        slim_results = [_slim_tool_for_planner(r) for r in found_tools]

        # Record events (maintain backward compatibility)
        self.context.record_event(
            "mcp.search.completed",
            {
                "query": query[:200],
                "detail_level": "full",
                "result_count": len(found_tools),
                "tool_ids": [r.get("tool_id") for r in found_tools if r.get("tool_id")],
            },
        )

        reasoning = command.get("reasoning") or ""
        self.context.record_step(
            type="search",
            command=command,
            success=True,
            preview=reasoning or f"Search '{query}' returned {len(found_tools)} results",
            output={"found_tools": slim_results},
            is_summary=False,
        )
        return None


def execute_mcp_task(
    task: str,
    *,
    user_id: str,
    budget: Budget | None = None,
    extra_context: Dict[str, Any] | None = None,
    toolbox_root: Path | None = None,
    llm: PlannerLLM | None = None,
) -> MCPTaskResult:
    """
    Execute a standalone MCP task and return a structured result.

    Args:
        task: Required natural-language request from the user.
        user_id: Required identifier used to scope MCP registry state.
        budget: Optional overrides for step/tool/code/cost ceilings.
        extra_context: Optional dict of metadata accessible to the planner.
        toolbox_root: Optional path to a generated toolbox (defaults to ./toolbox).

    Returns:
        MCPTaskResult: structure containing success, summary, budget usage, logs, and optional error.
    """

    if not isinstance(task, str) or not task.strip():
        raise ValueError("task must be a non-empty string.")
    normalized_user = normalize_user_id(user_id)
    resolved_toolbox = Path(toolbox_root).resolve() if toolbox_root else Path("toolbox").resolve()
    
    context = PlannerContext(
        task=task.strip(),
        user_id=normalized_user,
        budget=budget or Budget(),
        extra_context=extra_context or {},
        toolbox_root=resolved_toolbox,
    )
    for provider in ("gmail", "slack"):
        ensure_env_for_provider(normalized_user, provider)
    context.record_event(
        "mcp.planner.started",
        {
            "budget": asdict(context.budget_tracker.snapshot()),
            "extra_context_keys": sorted(context.extra_context.keys()),
        },
    )
    runtime = PlannerRuntime(context, llm=llm)
    result = runtime.run()
    # Guarantee a non-empty final_summary for callers that rely on it.
    success_flag = bool(result.get("success"))
    final_summary = result.get("final_summary")
    if not final_summary:
        result["final_summary"] = "Task completed." if success_flag else "Task failed."
    # Ensure raw_outputs / budget_usage / logs are always present even if a
    # custom runtime result omitted them.
    if "raw_outputs" not in result:
        result["raw_outputs"] = context.raw_outputs
    if "budget_usage" not in result:
        snapshot = context.budget_tracker.snapshot().to_dict()
        result["budget_usage"] = snapshot
    if "logs" not in result:
        result["logs"] = context.logs
    return result

