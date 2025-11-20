"""Action executor - routes actions to appropriate handlers.

This module provides the execute_action function which routes action commands
to the correct layer:
- search_tools -> knowledge layer
- call_tool -> actions layer
- run_code -> execution layer
- finish/fail -> terminal handlers

The executor is the "Doer" - it takes a command and returns an observation.
It does NOT make decisions about what to do next.

Responsibilities:
- Route action_type to correct handler
- Call handler with appropriate parameters
- Return standardized observations
- Track budget consumption

NOT responsible for:
- Deciding which action to take (orchestrator)
- Managing state (state.py)
- Formatting prompts (prompts.py)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from mcp_agent.core.context import AgentContext
    from .state import AgentState


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

    def execute_action(
        self,
        action_type: str,
        action_input: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Route action to appropriate handler and return observation.

        Args:
            action_type: One of: "search", "tool", "sandbox", "finish", "fail"
            action_input: Action-specific parameters

        Returns:
            Observation dict with:
                - success: bool
                - data: Any (action result)
                - error: Optional[str]
                - preview: str (human-readable summary)

        Raises:
            ValueError: If action_type is unknown
        """
        if action_type == "search":
            return self._execute_search(action_input)

        elif action_type == "tool":
            return self._execute_tool(action_input)

        elif action_type == "sandbox":
            return self._execute_sandbox(action_input)

        elif action_type == "finish":
            return self._execute_finish(action_input)

        elif action_type == "fail":
            return self._execute_fail(action_input)

        else:
            raise ValueError(f"Unknown action type: {action_type}")

    # --- Search execution ---

    def _execute_search(self, action_input: Dict[str, Any]) -> Dict[str, Any]:
        """Execute tool search and cache results.

        Args:
            action_input: {"query": str, "provider": Optional[str]}

        Returns:
            Observation with discovered tools
        """
        from mcp_agent.knowledge.search import search_tools
        from mcp_agent.knowledge.views import get_deep_view

        query = action_input.get("query", "")
        provider = action_input.get("provider")

        try:
            # Search for tools
            results = search_tools(
                query=query,
                provider=provider,
                detail_level="full",
                limit=10,
                user_id=self.agent_context.user_id,
            )

            # Extract tool IDs and get deep views
            tool_ids = [r.get("tool_id") or f"{r.get('provider')}.{r.get('tool')}" for r in results]

            # Get deep views for discovered tools
            deep_views = get_deep_view(self.agent_context, tool_ids)

            # Cache in state
            for view in deep_views:
                tool_id = view.get("tool_id")
                if tool_id:
                    self.agent_state.cache_tool_deep_view(tool_id, view)

            # Budget tracking
            self.agent_state.budget_tracker.steps += 1

            return {
                "success": True,
                "data": {
                    "found_tools": deep_views,
                    "count": len(deep_views)
                },
                "error": None,
                "preview": f"Found {len(deep_views)} tools matching '{query}'"
            }

        except Exception as exc:
            return {
                "success": False,
                "data": None,
                "error": str(exc),
                "preview": f"Search failed: {str(exc)[:100]}"
            }

    # --- Tool execution ---

    def _execute_tool(self, action_input: Dict[str, Any]) -> Dict[str, Any]:
        """Execute MCP tool call.

        Args:
            action_input: {
                "provider": str,
                "tool": str,
                "payload": Dict[str, Any]
            }

        Returns:
            Observation with tool result
        """
        from mcp_agent.actions.dispatcher import dispatch_tool
        from mcp_agent.execution.envelope import process_observation

        provider = action_input.get("provider")
        tool = action_input.get("tool")
        payload = action_input.get("payload", {})

        if not provider or not tool:
            return {
                "success": False,
                "data": None,
                "error": "Missing provider or tool name",
                "preview": "Tool call failed: missing parameters"
            }

        try:
            # Dispatch tool call
            result = dispatch_tool(
                context=self.agent_context,
                provider=provider,
                tool=tool,
                payload=payload
            )

            # Process and truncate for LLM observation
            observation = process_observation(self.agent_context, result)

            # Store raw output
            result_key = f"tool.{provider}.{tool}"
            self.agent_state.append_raw_output(result_key, {
                "type": "tool",
                "provider": provider,
                "tool": tool,
                "payload": payload,
                "response": result,
            })

            # Budget tracking
            self.agent_state.budget_tracker.tool_calls += 1
            self.agent_state.budget_tracker.steps += 1

            success = result.get("successful", False)
            preview = f"{provider}.{tool} " + ("succeeded" if success else "failed")

            return {
                "success": success,
                "data": observation,
                "error": result.get("error"),
                "preview": preview
            }

        except Exception as exc:
            return {
                "success": False,
                "data": None,
                "error": str(exc),
                "preview": f"{provider}.{tool} failed: {str(exc)[:100]}"
            }

    # --- Sandbox execution ---

    def _execute_sandbox(self, action_input: Dict[str, Any]) -> Dict[str, Any]:
        """Execute Python code in sandbox.

        Args:
            action_input: {
                "code": str,
                "label": Optional[str]
            }

        Returns:
            Observation with execution result
        """
        from mcp_agent.execution.sandbox import run_python_plan
        from mcp_agent.execution.envelope import process_observation

        code = action_input.get("code", "")
        label = action_input.get("label", "sandbox")

        if not code:
            return {
                "success": False,
                "data": None,
                "error": "No code provided",
                "preview": "Sandbox execution failed: no code"
            }

        try:
            # Execute in sandbox
            result = run_python_plan(
                context=self.agent_context,
                code_body=code,
                label=label
            )

            # Store raw output
            result_key = f"sandbox.{label}"
            self.agent_state.append_raw_output(result_key, {
                "type": "sandbox",
                "label": label,
                "code": code,
                "result": result.result,
                "logs": result.logs,
                "success": result.success,
            })

            # Process observation
            observation = process_observation(self.agent_context, result.result) if result.result else None

            # Budget tracking
            self.agent_state.budget_tracker.code_runs += 1
            self.agent_state.budget_tracker.steps += 1

            if result.success:
                return {
                    "success": True,
                    "data": observation,
                    "error": None,
                    "preview": f"Sandbox '{label}' succeeded"
                }
            else:
                return {
                    "success": False,
                    "data": result.logs,
                    "error": result.error,
                    "preview": f"Sandbox '{label}' failed: {result.error or 'unknown error'}"
                }

        except Exception as exc:
            return {
                "success": False,
                "data": None,
                "error": str(exc),
                "preview": f"Sandbox execution failed: {str(exc)[:100]}"
            }

    # --- Terminal actions ---

    def _execute_finish(self, action_input: Dict[str, Any]) -> Dict[str, Any]:
        """Mark execution as finished.

        Args:
            action_input: {"result": Any, "message": Optional[str]}

        Returns:
            Terminal observation
        """
        result = action_input.get("result")
        message = action_input.get("message", "Task completed successfully")

        self.agent_state.mark_finished(result)

        return {
            "success": True,
            "data": result,
            "error": None,
            "preview": message
        }

    def _execute_fail(self, action_input: Dict[str, Any]) -> Dict[str, Any]:
        """Mark execution as failed.

        Args:
            action_input: {"reason": str, "error": Optional[str]}

        Returns:
            Terminal observation
        """
        reason = action_input.get("reason", "Task failed")
        error = action_input.get("error")

        self.agent_state.mark_failed(reason)

        return {
            "success": False,
            "data": None,
            "error": error or reason,
            "preview": reason
        }


# --- Standalone function for backwards compatibility ---

def execute_action(
    agent_context: AgentContext,
    agent_state: AgentState,
    action_type: str,
    action_input: Dict[str, Any]
) -> Dict[str, Any]:
    """Execute action and return observation (standalone function).

    This is a convenience wrapper around ActionExecutor for use in
    existing code that doesn't want to manage an executor instance.

    Args:
        agent_context: Infrastructure context
        agent_state: Planning session state
        action_type: Action type ("search", "tool", "sandbox", "finish", "fail")
        action_input: Action parameters

    Returns:
        Observation dict with success, data, error, preview
    """
    executor = ActionExecutor(agent_context, agent_state)
    return executor.execute_action(action_type, action_input)
