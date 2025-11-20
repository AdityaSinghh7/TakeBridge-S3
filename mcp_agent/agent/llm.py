"""LLM interface for the MCP agent planner.

Migrated from planner/llm.py - handles LLM calls and message formatting.
"""

from __future__ import annotations

import os
import json
import sys
from typing import Any, Dict, List, TYPE_CHECKING

from shared.oai_client import OAIClient, extract_assistant_text

if TYPE_CHECKING:
    from mcp_agent.planner.context import PlannerContext
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

        if not self.is_enabled():
            context.record_event(
                "mcp.llm.skipped",
                {"model": self.model, "reason": "disabled"},
            )
            return {"messages": messages, "text": "", "response": None}

        client = self._get_client()
        json_mode_text = {"format": {"type": "json_object"}}
        json_mode_kwargs = {
            "model": self.model,
            "messages": messages,
            "reasoning_effort": "high",
            "max_output_tokens": 10000,
            "text": json_mode_text,
            "reasoning_summary": "auto",
        }
        try:
            response = client.create_response(**json_mode_kwargs)
        except TypeError as exc:
            # Older openai SDKs may not yet support `response_format`. Fall back gracefully.
            context.record_event(
                "mcp.llm.json_mode.unsupported",
                {"model": self.model, "error": str(exc)},
            )
            json_mode_kwargs.pop("text", None)
            response = client.create_response(**json_mode_kwargs)
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

    def is_enabled(self) -> bool:
        return self._llm_enabled()

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
        """
        Build the 3-message conversation:
          - system: planner prompt
          - developer: PLANNER_STATE_JSON
          - user: task + extra_context JSON payload
        """
        developer_content = self._developer_message(context, snapshot)
        user_payload = json.dumps(
            {"task": context.task, "extra_context": context.extra_context},
            ensure_ascii=False,
            sort_keys=True,
        )
        return [
            {"role": "system", "content": context.planner_prompt},
            {"role": "developer", "content": developer_content},
            {"role": "user", "content": user_payload},
        ]

    def _developer_message(
        self,
        context: PlannerContext,
        snapshot: BudgetSnapshot,
    ) -> str:
        state = context.planner_state(snapshot)
        state_json = json.dumps(state, ensure_ascii=False, sort_keys=True, indent=2)
        
        # DEBUG: optionally dump PLANNER_STATE_JSON to stderr
        if os.getenv("MCP_PLANNER_DUMP_STATE_JSON") == "1":
            print("\n================ PLANNER_STATE_JSON DUMP ================", file=sys.stderr)
            print(state_json, file=sys.stderr)
            print("=========================================================\n", file=sys.stderr)
        
        return f"PLANNER_STATE_JSON\n{state_json}"

