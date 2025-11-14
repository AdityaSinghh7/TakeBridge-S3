from __future__ import annotations

import os
from typing import Any, Dict, List

from shared.oai_client import OAIClient, extract_assistant_text

from .context import PlannerContext
from .budget import BudgetSnapshot


class PlannerLLM:
    """Helper that formats planner context and issues LLM calls via `shared.oai_client`."""

    def __init__(
        self,
        *,
        client: OAIClient | None = None,
        model: str = "o4-mini",
        enabled: bool | None = None,
    ) -> None:
        self._client = client
        self.model = model
        self._enabled_override = enabled

    def generate_plan(self, context: PlannerContext) -> Dict[str, Any]:
        snapshot = context.budget_tracker.snapshot()
        messages = self._build_messages(context, snapshot)

        if not self._llm_enabled():
            context.record_event(
                "mcp.llm.skipped",
                {"model": self.model, "reason": "disabled"},
            )
            return {"messages": messages, "text": "", "response": None}

        response = self._get_client().create_response(
            model=self.model,
            messages=messages,
            reasoning_effort="medium",
            max_output_tokens=1200,
        )
        context.token_tracker.record_response(self.model, "planner.llm", response)
        total_cost = getattr(context.token_tracker, "total_cost_usd", None)
        if isinstance(total_cost, (int, float)):
            context.budget_tracker.update_llm_cost(float(total_cost))
        text = extract_assistant_text(response) or ""
        context.record_event(
            "mcp.llm.completed",
            {"model": self.model, "output_chars": len(text)},
        )
        return {
            "messages": messages,
            "text": text,
            "response": response,
        }

    def _llm_enabled(self) -> bool:
        if self._enabled_override is not None:
            return self._enabled_override
        flag = os.getenv("MCP_PLANNER_LLM_ENABLED", "")
        return flag.lower() in {"1", "true", "yes", "on"}

    def _get_client(self) -> OAIClient:
        if self._client is None:
            self._client = OAIClient(default_model=self.model)
        return self._client

    def _build_messages(
        self,
        context: PlannerContext,
        snapshot: BudgetSnapshot,
    ) -> List[Dict[str, Any]]:
        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": context.planner_prompt},
            {
                "role": "user",
                "content": context.task,
            },
        ]
        developer_content = self._developer_message(context, snapshot)
        messages.append({"role": "developer", "content": developer_content})
        return messages

    def _developer_message(
        self,
        context: PlannerContext,
        snapshot: BudgetSnapshot,
    ) -> str:
        lines = [
            "You are the planner runtime. Use available tools/sandbox to solve the task.",
            f"Budget remaining: steps {snapshot.steps_taken}/{snapshot.max_steps}, "
            f"tool_calls {snapshot.tool_calls}/{snapshot.max_tool_calls}, "
            f"code_runs {snapshot.code_runs}/{snapshot.max_code_runs}, "
            f"llm_cost ${snapshot.estimated_llm_cost_usd:.4f}/{snapshot.max_llm_cost_usd:.2f}.",
        ]
        if context.tool_menu:
            lines.append("Top tools:")
            for tool in context.tool_menu[:5]:
                short = tool.get("short_description") or ""
                lines.append(
                    f"- {tool.get('qualified_name')} "
                    f"(available={tool.get('available')}) — {short}"
                )
        else:
            lines.append("No discovery results yet.")
        if context.tool_summaries:
            lines.append("Recent tool summaries:")
            for summary in context.tool_summaries[-3:]:
                lines.append(f"- {summary.get('label', 'tool')} :: {summary.get('notes', '')}")
        if context.sandbox_summaries:
            lines.append("Recent sandbox summaries:")
            for summary in context.sandbox_summaries[-2:]:
                lines.append(f"- {summary.get('label', 'sandbox')} :: {summary.get('notes', '')}")
        if context.extra_context:
            lines.append(f"Extra context keys: {', '.join(sorted(context.extra_context.keys()))}")
        return "\n".join(lines)
