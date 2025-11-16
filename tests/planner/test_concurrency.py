from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed

from mcp_agent.planner.runtime import execute_mcp_task


def test_execute_mcp_task_runs_concurrently_without_leak(monkeypatch):
    monkeypatch.setattr("mcp_agent.planner.runtime.perform_initial_discovery", lambda context: None)

    def fake_call_direct_tool(context, provider, tool, payload):
        context.append_raw_output(
            f"tool.{context.user_id}.{tool}",
            {
                "type": "tool",
                "provider": provider,
                "tool": tool,
                "payload": payload,
                "user_id": context.user_id,
                "response": {"successful": True},
            },
        )
        return {"successful": True}

    monkeypatch.setattr("mcp_agent.planner.runtime.call_direct_tool", fake_call_direct_tool)

    class ToolThenFinishLLM:
        def __init__(self, user_id: str) -> None:
            self.user_id = user_id
            self.calls = 0

        def generate_plan(self, context):
            if self.calls == 0:
                self.calls += 1
                return {
                    "text": json.dumps(
                        {
                            "type": "tool",
                            "provider": "slack",
                            "tool": "concurrency_probe",
                            "payload": {"user": context.user_id},
                            "reasoning": "Probe concurrency for this user.",
                        }
                    )
                }
            return {
                "text": json.dumps(
                    {
                        "type": "finish",
                        "summary": f"done-{self.user_id}",
                        "reasoning": "Tool call has completed.",
                    }
                )
            }

    # Provide a minimal index so tool validation passes.
    from mcp_agent.toolbox.models import ParameterSpec, ToolSpec
    from mcp_agent.toolbox.index import ToolboxIndex

    parameter = ParameterSpec(
        name="user",
        kind="positional_or_keyword",
        required=True,
        has_default=False,
        annotation="str",
        description=None,
    )
    tool_spec = ToolSpec(
        provider="slack",
        name="concurrency_probe",
        description="Probe concurrency",
        short_description="Probe concurrency",
        docstring="",
        python_name="concurrency_probe",
        python_signature="concurrency_probe(user: str)",
        parameters=[parameter],
        mcp_tool_name="CONCURRENCY_PROBE",
        oauth_provider="slack",
        oauth_required=True,
        available=True,
    )
    index = ToolboxIndex(providers={}, tools_by_id={tool_spec.tool_id: tool_spec})
    monkeypatch.setattr("mcp_agent.planner.runtime.get_index", lambda *args, **kwargs: index)

    def run_user(user_id: str):
        return execute_mcp_task("Concurrent task", user_id=user_id, llm=ToolThenFinishLLM(user_id))

    users = [f"user-{idx}" for idx in range(5)]
    with ThreadPoolExecutor(max_workers=len(users)) as executor:
        futures = {executor.submit(run_user, user): user for user in users}
        results = {}
        for future in as_completed(futures):
            user = futures[future]
            results[user] = future.result()

    for user_id, result in results.items():
        assert result["success"] is True
        assert result["final_summary"] == f"done-{user_id}"
        key = f"tool.{user_id}.concurrency_probe"
        assert key in result["raw_outputs"]
        payload = result["raw_outputs"][key][-1]["payload"]
        assert payload["user"] == user_id
