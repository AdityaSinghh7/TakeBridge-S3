"""Action executor - routes planner commands to appropriate handlers."""

from __future__ import annotations

import ast
import json
import traceback
from typing import TYPE_CHECKING, Any, Dict, List, Set

from mcp_agent.execution.envelope import unwrap_nested_data
from mcp_agent.execution.runner import run_python_plan
from mcp_agent.knowledge.search import search_tools
from mcp_agent.knowledge.introspection import get_index
from mcp_agent.actions.dispatcher import dispatch_tool
from mcp_agent.utils.token_counter import count_json_tokens
from mcp_agent.agent.observation_processor import summarize_observation
from shared import agent_signal

if TYPE_CHECKING:
    from mcp_agent.core.context import AgentContext
    from .state import AgentState
from .types import StepResult


def analyze_sandbox(code: str) -> tuple[Set[str], Dict[str, Set[str]], Dict[str, Dict[str, Dict[str, Any]]]]:
    """Analyze sandbox code to extract imported servers, function calls, and arg usage."""
    used_servers: Set[str] = set()
    calls_by_server: Dict[str, Set[str]] = {}
    call_details: Dict[str, Dict[str, Dict[str, Any]]] = {}

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
                detail = call_details.setdefault(server, {}).setdefault(
                    func_name, {"keywords": set(), "has_positional": False, "has_var_kw": False}
                )
                if node.args:
                    detail["has_positional"] = True
                for kw in node.keywords:
                    if kw.arg is None:
                        detail["has_var_kw"] = True
                    else:
                        detail["keywords"].add(kw.arg)
            self.generic_visit(node)

    tree = ast.parse(code)
    SandboxVisitor().visit(tree)
    return used_servers, calls_by_server, call_details


_RECOVERABLE_SANDBOX_ERRORS = {"KeyError", "IndexError", "AttributeError", "TypeError"}


def _extract_missing_key(error: Any) -> str | None:
    if not isinstance(error, str):
        return None
    stripped = error.strip()
    if len(stripped) >= 2 and stripped[0] == stripped[-1] and stripped[0] in {"'", '"'}:
        return stripped[1:-1]
    return None


def _is_dunder_main_guard(node: ast.AST) -> bool:
    if not isinstance(node, ast.Compare):
        return False
    left = node.left
    if not isinstance(left, ast.Name) or left.id != "__name__":
        return False
    if not any(isinstance(op, ast.Eq) for op in node.ops):
        return False
    for comparator in node.comparators:
        if isinstance(comparator, ast.Constant) and comparator.value == "__main__":
            return True
    return False


def _is_asyncio_run_call(node: ast.Call) -> bool:
    func = node.func
    return (
        isinstance(func, ast.Attribute)
        and isinstance(func.value, ast.Name)
        and func.value.id == "asyncio"
        and func.attr == "run"
    )


def _find_forbidden_sandbox_patterns(code: str) -> List[str]:
    patterns: List[str] = []
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return patterns

    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "main":
            patterns.append("async def main()")
            continue
        if isinstance(node, ast.FunctionDef) and node.name == "main":
            patterns.append("def main()")
            continue
        if isinstance(node, ast.If) and _is_dunder_main_guard(node.test):
            patterns.append("if __name__ == '__main__'")
            continue
        if isinstance(node, ast.Call) and _is_asyncio_run_call(node):
            patterns.append("asyncio.run(...)")
            continue

    return patterns


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
        agent_signal.raise_if_exit_requested()
        agent_signal.wait_for_resume()
        action_type = command.get("type")
        if action_type == "search":
            return self._execute_search(command)
        if action_type == "tool":
            return self._execute_tool(command)
        if action_type == "sandbox":
            return self._execute_sandbox(command)
        if action_type == "inspect_tool_output":
            return self._execute_inspect_tool_output(command)
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
        agent_signal.raise_if_exit_requested()
        agent_signal.wait_for_resume()
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

    def _execute_inspect_tool_output(self, command: Dict[str, Any]) -> StepResult:
        """Inspect a discovered tool's output schema at a specific field path."""
        agent_signal.raise_if_exit_requested()
        agent_signal.wait_for_resume()

        tool_id = (command.get("tool_id") or "").strip()
        field_path = (command.get("field_path") or "").strip()
        max_depth = command.get("max_depth", 4)
        max_fields = command.get("max_fields", 120)

        if not tool_id:
            return StepResult(
                type="inspect_tool_output",
                success=False,
                observation={"error": "inspect_tool_output missing tool_id."},
                preview="inspect_tool_output missing tool_id.",
                error="inspect_missing_tool_id",
                error_code="inspect_missing_tool_id",
            )
        if not isinstance(max_depth, int) or not isinstance(max_fields, int):
            return StepResult(
                type="inspect_tool_output",
                success=False,
                observation={"error": "inspect_tool_output max_depth/max_fields must be integers."},
                preview="inspect_tool_output max_depth/max_fields must be integers.",
                error="inspect_invalid_limits",
                error_code="inspect_invalid_limits",
            )

        # Enforce discovery: only inspect tools the planner has discovered via search.
        discovered_tool_ids = {
            entry.get("tool_id")
            for entry in self.agent_state.search_results
            if isinstance(entry, dict) and entry.get("tool_id")
        }
        if tool_id not in discovered_tool_ids:
            message = f"Tool '{tool_id}' was never discovered via search."
            return StepResult(
                type="inspect_tool_output",
                success=False,
                observation={"error": message},
                preview=message,
                error="planner_used_undiscovered_tool",
                error_code="planner_used_undiscovered_tool",
            )

        # Validate tool_id exists in index.
        index = get_index(self.agent_state.user_id)
        if index.get_tool(tool_id) is None:
            message = f"Unknown tool_id '{tool_id}'."
            return StepResult(
                type="inspect_tool_output",
                success=False,
                observation={"error": message},
                preview=message,
                error="planner_used_unknown_tool",
                error_code="planner_used_unknown_tool",
            )

        from mcp_agent.actions.wrappers.toolbox import inspect_tool_output

        result_key = f"inspect_tool_output.{tool_id}.{field_path or 'root'}"
        try:
            result = inspect_tool_output(
                self.agent_context,
                tool_id=tool_id,
                field_path=field_path,
                max_depth=max_depth,
                max_fields=max_fields,
            )
        except Exception as exc:
            error_message = str(exc)
            self.agent_state.append_raw_output(
                result_key,
                {
                    "type": "inspect_tool_output",
                    "tool_id": tool_id,
                    "field_path": field_path,
                    "error": error_message,
                },
            )
            return StepResult(
                type="inspect_tool_output",
                success=False,
                observation={"error": error_message},
                preview=f"inspect_tool_output failed: {error_message}",
                error=error_message,
                error_code="inspect_execution_failed",
                raw_output_key=result_key,
            )

        observation, is_smart_summary, original_tokens, compressed_tokens = self._process_tool_observation(result)
        self.agent_state.append_raw_output(
            result_key,
            {
                "type": "inspect_tool_output",
                "tool_id": tool_id,
                "field_path": field_path,
                "max_depth": max_depth,
                "max_fields": max_fields,
                "response": result,
            },
        )
        self.agent_state.budget_tracker.tool_calls += 1

        success_flag = True
        if isinstance(result, dict):
            success_flag = bool(result.get("successful", True))

        preview = command.get("reasoning") or f"inspect_tool_output({tool_id}, {field_path or 'root'})"
        return StepResult(
            type="inspect_tool_output",
            success=success_flag,
            observation=observation,
            preview=preview,
            raw_output_key=result_key,
            is_smart_summary=is_smart_summary,
            original_tokens=original_tokens,
            compressed_tokens=compressed_tokens,
        )

    # --- Observation processing with intelligent summarization ---

    def _process_tool_observation(self, result: Dict[str, Any]) -> tuple[Any, bool, int, int]:
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
            Tuple of (observation, is_smart_summary, original_tokens, compressed_tokens)
        """
        # Handle unsuccessful results - just return error
        if isinstance(result, dict):
            if "successful" in result and not result["successful"]:
                error_msg = result.get("error", "Unknown failure")
                error_data = {"successful": False, "error": error_msg}
                try:
                    error_tokens = count_json_tokens(error_data)
                except Exception:
                    error_tokens = 0
                return error_data, False, error_tokens, error_tokens

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
            return data, False, 0, 0

        # Log token count for monitoring
        self.agent_state.record_event(
            "mcp.observation.tool_tokens",
            {"token_count": token_count, "threshold": 8000}
        )

        # Decision: raw or summarize
        if token_count < 8000:
            return data, False, token_count, token_count

        # Summarize using LLM (no fallback - fail fast)
        summarized = summarize_observation(
            payload=data,
            payload_type="tool_result",
            original_tokens=token_count,
            context=self.agent_state,
        )

        # Count tokens in summarized output
        try:
            compressed_tokens = count_json_tokens(summarized)
        except Exception:
            compressed_tokens = token_count  # Fallback to original if counting fails

        return summarized, True, token_count, compressed_tokens

    def _process_sandbox_observation(self, result: Any) -> tuple[Any, bool, int, int]:
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
            Tuple of (observation, is_smart_summary, original_tokens, compressed_tokens)
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
            return result, False, 0, 0

        # Log token count for monitoring
        self.agent_state.record_event(
            "mcp.observation.sandbox_tokens",
            {"token_count": token_count, "threshold": 10000}
        )

        # Decision: raw or summarize
        if token_count < 10000:
            return result, False, token_count, token_count

        # Summarize using LLM (no fallback - fail fast)
        summarized = summarize_observation(
            payload=result,
            payload_type="sandbox_result",
            original_tokens=token_count,
            context=self.agent_state,
        )

        # Count tokens in summarized output
        try:
            compressed_tokens = count_json_tokens(summarized)
        except Exception:
            compressed_tokens = token_count  # Fallback to original if counting fails

        return summarized, True, token_count, compressed_tokens

    # --- Tool execution ---

    def _execute_tool(self, command: Dict[str, Any]) -> StepResult:
        """Execute MCP tool call with validation."""
        agent_signal.raise_if_exit_requested()
        agent_signal.wait_for_resume()
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
                tool_id=tool_id,
                provider=provider,
                server=server,
                tool_name=tool_name,
                args=args,
            )

        discovered_tool_ids = {
            entry.get("tool_id")
            for entry in (self.agent_state.search_results or [])
            if isinstance(entry, dict) and entry.get("tool_id")
        }
        has_search_steps = any(step.action_type == "search" for step in self.agent_state.history)
        if has_search_steps and tool_id not in discovered_tool_ids:
            return StepResult(
                type="tool",
                success=False,
                observation={"error": f"Tool '{tool_id}' was never discovered via search."},
                preview=f"Tool '{tool_id}' was never discovered via search.",
                error="planner_used_undiscovered_tool",
                error_code="planner_used_undiscovered_tool",
                tool_id=tool_id,
                provider=provider,
                server=server,
                tool_name=tool_name,
                args=args,
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
            agent_signal.raise_if_exit_requested()
            agent_signal.wait_for_resume()
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
                tool_id=tool_id,
                provider=provider,
                server=server,
                tool_name=tool_name,
                args=args,
            )

        observation, is_smart_summary, original_tokens, compressed_tokens = self._process_tool_observation(result)
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
            original_tokens=original_tokens,
            compressed_tokens=compressed_tokens,
            tool_id=tool_id,
            provider=provider,
            server=server,
            tool_name=tool_name,
            args=payload,
        )

    # --- Sandbox execution ---

    def _check_all_tools_succeeded(self, result: Any) -> bool:
        """
        Check if all tool calls within a sandbox result succeeded.

        Uses heuristics to determine success:
        1. If result contains explicit error → False
        2. If result contains MCP tool envelopes, check those
        3. If result doesn't have errors and has meaningful data → True

        This helps the model determine if a sandbox execution fully completed
        its intended operations without needing to re-run the same logic.

        Args:
            result: The sandbox execution result (typically a dict)

        Returns:
            True if ALL tool calls succeeded, False otherwise
        """
        if not isinstance(result, dict):
            # If result isn't a dict, we can't determine success
            return False

        # Check for explicit error at top level
        if "error" in result and result["error"]:
            return False

        found_any_tool_response = False
        all_envelopes_succeeded = True
        found_error = False

        def check_dict(obj: Any) -> bool:
            """Recursively check if all tool responses in obj are successful."""
            nonlocal found_any_tool_response, all_envelopes_succeeded, found_error

            if not isinstance(obj, dict):
                return True

            # Check if this looks like a canonical MCP tool response envelope
            # Require a data field plus a success indicator.
            has_success_key = any(key in obj for key in ("successful", "successfull", "success"))
            if has_success_key and "data" in obj:
                found_any_tool_response = True
                # Check tool success using the canonical response ops logic
                from mcp_agent.execution.response_ops import MCPResponseOps

                if not MCPResponseOps(obj).is_success():
                    all_envelopes_succeeded = False
                    return False
            elif "error" in obj and obj.get("error") not in (None, "", False):
                found_error = True
                all_envelopes_succeeded = False
                return False

            # Recursively check nested dicts and lists
            for value in obj.values():
                if isinstance(value, dict):
                    if not check_dict(value):
                        return False
                elif isinstance(value, list):
                    for item in value:
                        if isinstance(item, dict):
                            if not check_dict(item):
                                return False

            return True

        check_dict(result)

        if found_error:
            return False

        # Strategy:
        # 1. If we found tool envelopes, use those to determine success
        if found_any_tool_response:
            return all_envelopes_succeeded

        # 2. If no envelopes found but result has no errors and has data → assume success
        # This handles cases where sandbox extracts specific fields rather than
        # preserving full tool response envelopes
        if not result.get("error"):
            # Consider it successful if result has meaningful content
            # (not just empty dicts/lists)
            has_content = any(
                v for k, v in result.items()
                if k != "_all_tools_succeeded" and v not in (None, {}, [])
            )
            return has_content

        # 3. Default to False if we can't determine
        return False

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
            used_servers, calls_by_server, call_details = analyze_sandbox(code_body)
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
                    step.action_type == "sandbox"
                    and step.error == "sandbox_syntax_error"
                    and (step.action_input.get("label") or "").strip() == label
                ):
                    prior_errors += 1
            lineno = getattr(exc, "lineno", None)
            msg = getattr(exc, "msg", str(exc))
            error_text = f"Sandbox syntax error at line {lineno or '?'}: {msg}. Ensure code has real newlines and escaped quotes"
            observation = {
                "error": error_text,
                "label": label,
                "prior_errors": prior_errors,
                "code_preview": code_body[:400],
            }
            return StepResult(
                type="sandbox",
                success=False,
                observation=observation,
                preview=error_text,
                error="sandbox_syntax_error",
                error_code="sandbox_syntax_error",
                raw_output_key=f"sandbox.{label}",
            )

        forbidden_patterns = _find_forbidden_sandbox_patterns(code_body)
        if forbidden_patterns:
            prior_errors = 0
            for step in self.agent_state.history:
                if (
                    step.action_type == "sandbox"
                    and step.error == "sandbox_invalid_body"
                    and (step.action_input.get("label") or "").strip() == label
                ):
                    prior_errors += 1
            hint = (
                "Sandbox code must be ONLY the body of the pre-defined async def main(); "
                "remove wrappers like async def main(), def main(), if __name__ == '__main__', "
                "and asyncio.run(...). Return a JSON-serializable dict."
            )
            message = "Sandbox code contains forbidden wrapper patterns: " + ", ".join(forbidden_patterns)
            self.agent_state.record_event(
                "mcp.sandbox.invalid_body",
                {
                    "label": label,
                    "patterns": forbidden_patterns,
                    "code_preview": code_body[:4000],
                },
            )
            observation = {
                "error": message,
                "label": label,
                "patterns": forbidden_patterns,
                "prior_errors": prior_errors,
                "recoverable": True,
                "hint": hint,
            }
            return StepResult(
                type="sandbox",
                success=False,
                observation=observation,
                preview=message,
                error="sandbox_invalid_body",
                error_code="sandbox_invalid_body",
                raw_output_key=f"sandbox.{label}",
            )

        has_tool_calls = any(calls_by_server.values())

        def _extract_func_name(entry: Dict[str, Any]) -> str | None:
            signature = entry.get("signature")
            if isinstance(signature, str) and "(" in signature:
                head = signature.split("(", 1)[0]
                if "." in head:
                    return head.rsplit(".", 1)[-1]
                return head
            return entry.get("py_name") or entry.get("tool")

        allowed_servers = {
            (entry.get("server") or entry.get("provider"))
            for entry in self.agent_state.search_results
            if entry.get("server") or entry.get("provider")
        }
        allowed_funcs_by_server: Dict[str, Set[str]] = {}
        param_schemas_by_server: Dict[str, Dict[str, Dict[str, Set[str]]]] = {}
        for entry in self.agent_state.search_results:
            server = (entry.get("server") or entry.get("provider"))
            func_name = _extract_func_name(entry)
            if not (server and func_name):
                continue
            allowed_funcs_by_server.setdefault(server, set()).add(func_name)
            input_params = entry.get("input_params")
            if not input_params:
                continue  # No schema available; keep function discovery only
            all_params = {name for name in input_params.keys()}
            required_params = {
                name
                for name, desc in input_params.items()
                if isinstance(desc, str) and "required" in desc.lower()
            }
            param_schemas_by_server.setdefault(server, {})[func_name] = {
                "all_params": all_params,
                "required_params": required_params,
            }

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
            if server not in allowed_servers:
                # Ignore attribute access on non-provider variables (e.g., loop vars like "doc")
                continue
            allowed_funcs = allowed_funcs_by_server.get(server, set())
            if not allowed_funcs:
                message = f"Sandbox used '{server}' functions but none were discovered via search."
                return StepResult(
                    type="sandbox",
                    success=False,
                    observation={"error": message},
                    preview=message,
                    error="planner_used_undiscovered_tool",
                    error_code="planner_used_undiscovered_tool",
                )
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

        # Validate keyword args against discovered tool schemas
        for server, funcs in call_details.items():
            for func_name, detail in funcs.items():
                schema = param_schemas_by_server.get(server, {}).get(func_name)
                if not schema:
                    continue  # No schema; do not block to avoid false positives
                provided = detail.get("keywords", set()) or set()
                unknown_params = provided - schema["all_params"]
                missing_params = schema["required_params"] - provided

                problems: List[str] = []
                if unknown_params:
                    problems.append(
                        f"unexpected args: {', '.join(sorted(unknown_params))}"
                    )
                if missing_params:
                    problems.append(
                        f"missing required args: {', '.join(sorted(missing_params))}"
                    )
                if detail.get("has_positional"):
                    problems.append("positional args detected; use keyword args as per signature")
                if detail.get("has_var_kw"):
                    problems.append("var-keyword (**kwargs) usage is not allowed in sandbox calls")

                if problems:
                    allowed_list = ", ".join(sorted(schema["all_params"])) or "none"
                    problem_text = " ; ".join(problems)
                    message = (
                        f"Sandbox call '{server}.{func_name}' has invalid arguments: "
                        f"{problem_text}. Allowed args: {allowed_list}."
                    )
                    return StepResult(
                        type="sandbox",
                        success=False,
                        observation={
                            "error": message,
                            "server": server,
                            "function": func_name,
                        },
                        preview=message,
                        error="sandbox_invalid_args",
                        error_code="sandbox_invalid_args",
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
        self.agent_state.record_event(
            "mcp.sandbox.run",
            {
                "success": sandbox_result.success,
                "timed_out": sandbox_result.timed_out,
                "log_lines": len(sandbox_result.logs),
                "code_preview": code_body,
                "label": label,
            },
        )

        normalized_result = unwrap_nested_data(sandbox_result.result)
        result_key = f"sandbox.{label}"

        # Check if all tool calls within the sandbox succeeded
        all_tools_succeeded = self._check_all_tools_succeeded(normalized_result)

        entry = {
            "type": "sandbox",
            "label": label,
            "success": sandbox_result.success,
            "timed_out": sandbox_result.timed_out,
            "logs": sandbox_result.logs,
            "error": sandbox_result.error,
            "result": normalized_result,
            "code_preview": code_body[:1200],
            "all_tools_succeeded": all_tools_succeeded,
        }
        self.agent_state.append_raw_output(result_key, entry)

        if normalized_result is not None:
            summary = self.agent_state.summarize_sandbox_output(label, normalized_result)
            if summary:
                entry["summary"] = summary

        runtime_error: str | None = None
        if sandbox_result.success and not sandbox_result.timed_out and isinstance(normalized_result, dict):
            if normalized_result.get("successful") is False:
                runtime_error = normalized_result.get("error") or "sandbox returned successful=False"
            elif normalized_result.get("error"):
                runtime_error = normalized_result.get("error")
            elif normalized_result.get("traceback"):
                runtime_error = "sandbox raised an exception"

        if sandbox_result.success and not sandbox_result.timed_out and runtime_error:
            logs = sandbox_result.logs or []
            MAX_LOG_LINES = 50
            if len(logs) > MAX_LOG_LINES:
                logs = logs[:MAX_LOG_LINES] + ["... (truncated)"]
            preview = command.get("reasoning") or f"Sandbox '{label}' failed: {runtime_error[:100]}"
            error_payload = {
                "error": runtime_error,
                "logs": logs,
                "result": normalized_result,
                "timed_out": False,
            }
            error_type = None
            missing_key = None
            if isinstance(normalized_result, dict):
                error_type = normalized_result.get("error_type")
                if error_type == "KeyError":
                    missing_key = _extract_missing_key(normalized_result.get("error"))

            recoverable = error_type in _RECOVERABLE_SANDBOX_ERRORS
            error_code = "sandbox_logic_error" if recoverable else "sandbox_runtime_error"
            if error_type:
                error_payload["error_type"] = error_type
            if missing_key:
                error_payload["missing_key"] = missing_key
            if recoverable:
                prior_errors = 0
                for step in self.agent_state.history:
                    if (
                        step.action_type == "sandbox"
                        and step.error == error_code
                        and (step.action_input.get("label") or "").strip() == label
                    ):
                        prior_errors += 1
                error_payload["prior_errors"] = prior_errors
                error_payload["recoverable"] = True
                error_payload["hint"] = (
                    "Sandbox code accessed missing/invalid data; check response keys before indexing."
                )
            return StepResult(
                type="sandbox",
                success=False,
                observation=error_payload,
                preview=preview,
                error=runtime_error,
                error_code=error_code,
                raw_output_key=result_key,
            )

        if (
            sandbox_result.success
            and not sandbox_result.timed_out
            and has_tool_calls
            and (normalized_result is None or normalized_result == {})
        ):
            prior_errors = 0
            for step in self.agent_state.history:
                if (
                    step.action_type == "sandbox"
                    and step.error == "sandbox_empty_result"
                    and (step.action_input.get("label") or "").strip() == label
                ):
                    prior_errors += 1
            hint = (
                "Sandbox returned an empty result after tool calls. Return a JSON-serializable dict from main() "
                "and do NOT wrap it in your own async def main() or asyncio.run(...)."
            )
            error_payload = {
                "error": "sandbox returned empty result",
                "label": label,
                "result": normalized_result,
                "prior_errors": prior_errors,
                "recoverable": True,
                "hint": hint,
            }
            preview = command.get("reasoning") or "Sandbox returned empty result"
            return StepResult(
                type="sandbox",
                success=False,
                observation=error_payload,
                preview=preview,
                error="sandbox_empty_result",
                error_code="sandbox_empty_result",
                raw_output_key=result_key,
            )

        if sandbox_result.success and not sandbox_result.timed_out:
            observation, is_smart_summary, original_tokens, compressed_tokens = self._process_sandbox_observation(sandbox_result.result)
            preview = command.get("reasoning") or f"Sandbox '{label}' success"
            # Add metadata about tool success to the observation
            if isinstance(observation, dict) and not observation.get("error"):
                observation["_all_tools_succeeded"] = all_tools_succeeded
            return StepResult(
                type="sandbox",
                success=True,
                observation=observation,
                preview=preview,
                raw_output_key=result_key,
                is_smart_summary=is_smart_summary,
                original_tokens=original_tokens,
                compressed_tokens=compressed_tokens,
            )

        # Failure path: propagate stderr/logs to the observation and error fields
        error_details = sandbox_result.error or ("sandbox timed out" if sandbox_result.timed_out else "sandbox_execution_failed")
        # Truncate logs to a reasonable number of lines to avoid huge observations
        logs = sandbox_result.logs or []
        MAX_LOG_LINES = 50
        if len(logs) > MAX_LOG_LINES:
            logs = logs[:MAX_LOG_LINES] + ["... (truncated)"]

        error_payload = {
            "error": error_details,
            "logs": logs,
            "timed_out": sandbox_result.timed_out,
        }

        # If the result contains traceback or additional error info, include it
        if isinstance(normalized_result, dict):
            if "traceback" in normalized_result:
                error_payload["traceback"] = normalized_result["traceback"]
            if "error_type" in normalized_result:
                error_payload["error_type"] = normalized_result["error_type"]
            # Include the full error message from the result if available
            if normalized_result.get("error"):
                error_details = normalized_result["error"]
                error_payload["error"] = error_details

        preview = command.get("reasoning") or f"Sandbox '{label}' failed: {error_details[:100]}"
        error_code = "sandbox_timeout" if sandbox_result.timed_out else "sandbox_runtime_error"
        return StepResult(
            type="sandbox",
            success=False,
            observation=error_payload,
            preview=preview,
            error=error_details,
            error_code=error_code,
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
