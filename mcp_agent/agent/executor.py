"""Action executor - routes planner commands to appropriate handlers."""

from __future__ import annotations

from __future__ import annotations

import ast
import json
import traceback
from typing import TYPE_CHECKING, Any, Dict, List, Set

from mcp_agent.execution.envelope import unwrap_nested_data
from mcp_agent.execution.sandbox import run_python_plan
from mcp_agent.knowledge.search import search_tools
from mcp_agent.knowledge.builder import get_index
from mcp_agent.actions.dispatcher import dispatch_tool
from mcp_agent.utils.token_counter import count_json_tokens
from mcp_agent.agent.observation_processor import summarize_observation

if TYPE_CHECKING:
    from mcp_agent.core.context import AgentContext
    from .state import AgentState
from .types import StepResult


def analyze_sandbox(code: str) -> tuple[Set[str], Dict[str, Set[str]]]:
    """Analyze sandbox code to extract imported servers and function calls."""
    used_servers: Set[str] = set()
    calls_by_server: Dict[str, Set[str]] = {}

    class SandboxVisitor(ast.NodeVisitor):
        def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
            if node.module == "sandbox_py.servers":
                for alias in node.names:
                    used_servers.add(alias.name)
            self.generic_visit(node)

        def visit_Import(self, node: ast.Import) -> None:
            for alias in node.names:
                if alias.name.startswith("sandbox_py.servers."):
                    server = alias.name.split(".")[-1]
                    used_servers.add(server)
            self.generic_visit(node)

        def visit_Call(self, node: ast.Call) -> None:
            func = node.func
            if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
                server = func.value.id
                func_name = func.attr
                calls_by_server.setdefault(server, set()).add(func_name)
            self.generic_visit(node)

    tree = ast.parse(code)
    SandboxVisitor().visit(tree)
    return used_servers, calls_by_server


class ActionExecutor:
    """Routes actions to appropriate handlers and returns observations."""

    def __init__(self, agent_context: AgentContext, agent_state: AgentState):
        """Initialize executor with contexts.

        Args:
            agent_context: Infrastructure context (user_id, db, etc.)
            agent_state: Planning session state
        """
        self.agent_context = agent_context
        self.agent_state = agent_state

    def execute_step(self, command: Dict[str, Any]) -> StepResult:
        """Execute a planner command and return a structured result.

        Args:
            command: Parsed command dict from the planner parser.

        Returns:
            StepResult containing success flag, preview text, observation payload, etc.
        """
        action_type = command.get("type")
        if action_type == "search":
            return self._execute_search(command)
        if action_type == "tool":
            return self._execute_tool(command)
        if action_type == "sandbox":
            return self._execute_sandbox(command)
        if action_type == "finish":
            return self._execute_finish(command)
        if action_type == "fail":
            return self._execute_fail(command)
        return StepResult(
            type="fail",
            success=False,
            observation={"error": f"Unknown command type: {action_type}"},
            preview=f"Unknown command type: {action_type}",
            error="unknown_command",
        )

    # --- Search execution ---

    def _execute_search(self, command: Dict[str, Any]) -> StepResult:
        """Execute tool search and cache results.

        Args:
            action_input: {"query": str, "provider": Optional[str]}

        Returns:
            Observation with discovered tools
        """
        query = (command.get("query") or "").strip()
        provider = command.get("provider")

        if not query:
            return StepResult(
                type="search",
                success=False,
                observation={"error": "Search command missing query."},
                preview="Search command missing query.",
                error="search_missing_query",
                error_code="search_missing_query",
            )

        try:
            # Search for tools - now returns compact descriptors
            results = search_tools(
                query=query,
                provider=provider,
                detail_level="full",
                limit=10,
                user_id=self.agent_context.user_id,
            )

            # Store compact results directly in state (no need for deep views)
            self.agent_state.merge_search_results(results)

            # Budget tracking
            self.agent_state.budget_tracker.steps_taken += 1

            return StepResult(
                type="search",
                success=True,
                observation={"found_tools": results, "count": len(results)},
                preview=f"Found {len(results)} tools matching '{query}'",
                raw_output_key=None,
            )

        except Exception as exc:
            return StepResult(
                type="search",
                success=False,
                observation={"error": str(exc)},
                preview=f"Search failed: {str(exc)[:100]}",
                error=str(exc),
                error_code="search_failed",
            )

    # --- Observation processing with intelligent summarization ---

    def _process_tool_observation(self, result: Dict[str, Any]) -> tuple[Any, bool]:
        """
        Process tool execution result with intelligent summarization.

        Strategy:
        1. Check successful/error envelope
        2. Count tokens in data payload
        3. If < 8000 tokens: return raw data
        4. If >= 8000 tokens: LLM-summarize maintaining structure

        Args:
            result: Raw tool execution response envelope

        Returns:
            Processed observation (raw or summarized)
        """
        # Handle unsuccessful results - just return error
        if isinstance(result, dict):
            if "successful" in result and not result["successful"]:
                error_msg = result.get("error", "Unknown failure")
                return {"successful": False, "error": error_msg}, False

        # Extract data payload
        if isinstance(result, dict) and "data" in result:
            data = result["data"]
        else:
            data = result

        # Count tokens in data payload
        try:
            token_count = count_json_tokens(data)
        except Exception as e:
            self.agent_state.record_event(
                "mcp.observation.token_count_failed",
                {"error": str(e), "type": "tool"}
            )
            # Fallback to raw if counting fails
            return data, False

        # Log token count for monitoring
        self.agent_state.record_event(
            "mcp.observation.tool_tokens",
            {"token_count": token_count, "threshold": 8000}
        )

        # Decision: raw or summarize
        if token_count < 8000:
            return data, False

        # Summarize using LLM (no fallback - fail fast)
        summarized = summarize_observation(
            payload=data,
            payload_type="tool_result",
            original_tokens=token_count,
            context=self.agent_state,
        )
        return summarized, True

    def _process_sandbox_observation(self, result: Any) -> tuple[Any, bool]:
        """
        Process sandbox execution result with intelligent summarization.

        Strategy:
        1. Take full result object (no envelope unwrapping needed)
        2. Count tokens in result
        3. If < 10000 tokens: return raw result
        4. If >= 10000 tokens: LLM-summarize maintaining structure

        Args:
            result: Raw sandbox execution result (any shape)

        Returns:
            Processed observation (raw or summarized)
        """
        # Count tokens in full result
        try:
            token_count = count_json_tokens(result)
        except Exception as e:
            self.agent_state.record_event(
                "mcp.observation.token_count_failed",
                {"error": str(e), "type": "sandbox"}
            )
            # Fallback to raw if counting fails
            return result, False

        # Log token count for monitoring
        self.agent_state.record_event(
            "mcp.observation.sandbox_tokens",
            {"token_count": token_count, "threshold": 10000}
        )

        # Decision: raw or summarize
        if token_count < 10000:
            return result, False

        # Summarize using LLM (no fallback - fail fast)
        summarized = summarize_observation(
            payload=result,
            payload_type="sandbox_result",
            original_tokens=token_count,
            context=self.agent_state,
        )
        return summarized, True

    # --- Tool execution ---

    def _execute_tool(self, command: Dict[str, Any]) -> StepResult:
        """Execute MCP tool call with validation."""
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
                return StepResult(
                    type="tool",
                    success=False,
                    observation={"error": "Tool command 'args' must be an object."},
                    preview="Tool command 'args' must be an object.",
                    error="tool_invalid_args",
                    error_code="tool_invalid_args",
                )
        else:
            if not provider or not tool_name:
                return StepResult(
                    type="tool",
                    success=False,
                    observation={"error": "Tool command missing provider/tool."},
                    preview="Tool command missing provider/tool.",
                    error="tool_missing_fields",
                    error_code="tool_missing_fields",
                )
            if payload is None:
                payload = {}
            if not isinstance(payload, dict):
                return StepResult(
                    type="tool",
                    success=False,
                    observation={"error": "Tool command 'payload' must be an object."},
                    preview="Tool command 'payload' must be an object.",
                    error="tool_invalid_payload",
                    error_code="tool_invalid_payload",
                )
            tool_id = f"{provider}.{tool_name}"
            server = provider
            args = payload

        index = get_index(self.agent_state.user_id)
        spec = index.get_tool(tool_id)
        if spec is None:
            return StepResult(
                type="tool",
                success=False,
                observation={"error": f"Unknown tool_id '{tool_id}'."},
                preview=f"Unknown tool_id '{tool_id}'.",
                error="planner_used_unknown_tool",
                error_code="planner_used_unknown_tool",
            )

        discovered_tool_ids = {
            entry.get("tool_id")
            for entry in self.agent_state.search_results
            if entry.get("tool_id")
        }
        has_search_steps = any(step.type == "search" for step in self.agent_state.history)
        if has_search_steps and tool_id not in discovered_tool_ids:
            return StepResult(
                type="tool",
                success=False,
                observation={"error": f"Tool '{tool_id}' was never discovered via search."},
                preview=f"Tool '{tool_id}' was never discovered via search.",
                error="planner_used_undiscovered_tool",
                error_code="planner_used_undiscovered_tool",
            )

        provider = spec.provider
        tool_name = spec.name
        payload = args or {}
        resolved_tool = self.agent_state.resolve_mcp_tool_name(provider, tool_name)
        command.setdefault("provider", provider)
        command.setdefault("tool", tool_name)
        command.setdefault("resolved_tool", resolved_tool)
        self.agent_state.record_event(
            "mcp.action.planned",
            {"provider": provider, "tool": resolved_tool},
        )

        result_key = f"tool.{provider}.{resolved_tool}"

        try:
            clean_payload = {k: v for k, v in payload.items() if k != "context"}
            result = dispatch_tool(
                context=self.agent_context,
                provider=provider,
                tool=tool_name,
                payload=clean_payload,
            )
        except Exception as exc:
            error_message = str(exc)
            trace = "".join(traceback.format_exception(exc))
            self.agent_state.record_event(
                "mcp.action.exception",
                {
                    "provider": provider,
                    "tool": resolved_tool,
                    "error": error_message,
                    "traceback": trace[-2000:],
                },
            )
            return StepResult(
                type="tool",
                success=False,
                observation={"error": error_message},
                preview=f"{provider}.{resolved_tool} failed: {error_message}",
                error=error_message,
                error_code="tool_execution_failed",
            )

        observation, is_smart_summary = self._process_tool_observation(result)
        self.agent_state.append_raw_output(
            result_key,
            {
                "type": "tool",
                "provider": provider,
                "tool": tool_name,
                "payload": payload,
                "response": result,
            },
        )
        self.agent_state.budget_tracker.tool_calls += 1
        self.agent_state.budget_tracker.steps_taken += 1

        success_flag = True
        if isinstance(result, dict):
            success_flag = result.get("successful", True)

        self.agent_state.record_event(
            "mcp.action.completed",
            {"provider": provider, "tool": resolved_tool},
        )

        preview = command.get("reasoning") or f"{provider}.{resolved_tool} (successful={success_flag})"
        return StepResult(
            type="tool",
            success=success_flag,
            observation=observation,
            preview=preview,
            raw_output_key=result_key,
            is_smart_summary=is_smart_summary,
        )

    # --- Sandbox execution ---

    def _execute_sandbox(self, command: Dict[str, Any]) -> StepResult:
        """Execute Python code in sandbox with static validation."""
        code_body = command.get("code")
        if not code_body:
            return StepResult(
                type="sandbox",
                success=False,
                observation={"error": "Sandbox command missing code body."},
                preview="Sandbox command missing code body.",
                error="sandbox_missing_code",
                error_code="sandbox_missing_code",
            )

        label = (command.get("label") or "sandbox").strip() or "sandbox"

        try:
            used_servers, calls_by_server = analyze_sandbox(code_body)
        except SyntaxError as exc:
            self.agent_state.record_event(
                "mcp.sandbox.syntax_error",
                {
                    "label": label,
                    "error": str(exc),
                    "code_preview": code_body[:4000],
                },
            )
            prior_errors = 0
            for step in self.agent_state.history:
                if (
                    step.type == "sandbox"
                    and step.error == "sandbox_syntax_error"
                    and (step.command.get("label") or "").strip() == label
                ):
                    prior_errors += 1
            observation = {
                "error": f"Sandbox code has invalid syntax: {exc}",
                "label": label,
                "prior_errors": prior_errors,
            }
            return StepResult(
                type="sandbox",
                success=False,
                observation=observation,
                preview=observation["error"],
                error="sandbox_syntax_error",
                error_code="sandbox_syntax_error",
                raw_output_key=f"sandbox.{label}",
            )

        allowed_servers = {
            (entry.get("server") or entry.get("provider"))
            for entry in self.agent_state.search_results
            if entry.get("server") or entry.get("provider")
        }
        allowed_py_names_by_server: Dict[str, Set[str]] = {}
        for entry in self.agent_state.search_results:
            server = (entry.get("server") or entry.get("provider"))
            py_name = entry.get("py_name") or entry.get("tool")
            if server and py_name:
                allowed_py_names_by_server.setdefault(server, set()).add(py_name)

        for server in used_servers:
            if server not in allowed_servers:
                message = f"Sandbox used server '{server}' which was never discovered via search."
                return StepResult(
                    type="sandbox",
                    success=False,
                    observation={"error": message},
                    preview=message,
                    error="planner_used_unknown_server",
                    error_code="planner_used_unknown_server",
                )

        for server, funcs in calls_by_server.items():
            if server not in allowed_py_names_by_server:
                continue
            allowed_funcs = allowed_py_names_by_server.get(server, set())
            for func in funcs:
                if func not in allowed_funcs:
                    message = f"Sandbox used '{server}.{func}' which was not in search results."
                    return StepResult(
                        type="sandbox",
                        success=False,
                        observation={"error": message},
                        preview=message,
                        error="planner_used_undiscovered_tool",
                        error_code="planner_used_undiscovered_tool",
                    )

        try:
            sandbox_result = run_python_plan(
                context=self.agent_context,
                code_body=code_body,
                label=label,
            )
        except Exception as exc:
            return StepResult(
                type="sandbox",
                success=False,
                observation={"error": str(exc)},
                preview=f"Sandbox execution failed: {str(exc)[:100]}",
                error="sandbox_runtime_error",
                error_code="sandbox_runtime_error",
            )

        self.agent_state.budget_tracker.code_runs += 1
        self.agent_state.budget_tracker.steps_taken += 1
        self.agent_state.record_event(
            "mcp.sandbox.run",
            {
                "success": sandbox_result.success,
                "timed_out": sandbox_result.timed_out,
                "log_lines": len(sandbox_result.logs),
                "code_preview": code_body[:200],
                "label": label,
            },
        )

        normalized_result = unwrap_nested_data(sandbox_result.result)
        result_key = f"sandbox.{label}"
        entry = {
            "type": "sandbox",
            "label": label,
            "success": sandbox_result.success,
            "timed_out": sandbox_result.timed_out,
            "logs": sandbox_result.logs,
            "error": sandbox_result.error,
            "result": normalized_result,
            "code_preview": code_body[:1200],
        }
        self.agent_state.append_raw_output(result_key, entry)

        if normalized_result is not None:
            summary = self.agent_state.summarize_sandbox_output(label, normalized_result)
            if summary:
                entry["summary"] = summary

        if sandbox_result.success:
            observation, is_smart_summary = self._process_sandbox_observation(sandbox_result.result)
            preview = command.get("reasoning") or f"Sandbox '{label}' success"
            return StepResult(
                type="sandbox",
                success=True,
                observation=observation,
                preview=preview,
                raw_output_key=result_key,
                is_smart_summary=is_smart_summary,
            )

        error_payload = {
            "error": sandbox_result.error or "sandbox_execution_failed",
            "logs": sandbox_result.logs,
        }
        preview = command.get("reasoning") or f"Sandbox '{label}' failed"
        return StepResult(
            type="sandbox",
            success=False,
            observation=error_payload,
            preview=preview,
            error="sandbox_runtime_error",
            error_code="sandbox_runtime_error",
            raw_output_key=result_key,
        )

    # --- Terminal actions ---

    def _execute_finish(self, command: Dict[str, Any]) -> StepResult:
        """Mark execution as finished.

        Args:
            action_input: {"result": Any, "message": Optional[str]}

        Returns:
            Terminal observation
        """
        result = command.get("result")
        message = command.get("message", "Task completed successfully")

        self.agent_state.mark_finished(result)

        return StepResult(
            type="finish",
            success=True,
            observation=result,
            preview=message,
        )

    def _execute_fail(self, command: Dict[str, Any]) -> StepResult:
        """Mark execution as failed.

        Args:
            action_input: {"reason": str, "error": Optional[str]}

        Returns:
            Terminal observation
        """
        reason = command.get("reason", "Task failed")
        error = command.get("error")

        self.agent_state.mark_failed(reason)

        return StepResult(
            type="fail",
            success=False,
            observation={"error": error or reason},
            preview=reason,
            error=error or reason,
        )
