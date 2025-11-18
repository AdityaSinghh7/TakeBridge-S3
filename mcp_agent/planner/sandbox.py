from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

from mcp_agent.sandbox.runner import SandboxResult, run_python_plan
from mcp_agent.toolbox.envelope import unwrap_nested_data

from .context import PlannerContext


@dataclass
class SandboxExecutionResult:
    result: SandboxResult
    code_body: str


def run_sandbox_plan(
    context: PlannerContext,
    code_body: str,
    *,
    toolbox_root: Path | None = None,
    timeout_sec: int = 30,
    label: str = "sandbox",
) -> SandboxExecutionResult:
    """
    Planner-friendly wrapper around run_python_plan.

    Increments the sandbox code_run budget, records events, persists raw
    outputs under `sandbox.{label}`, and attaches optional summaries.
    """
    context.budget_tracker.code_runs += 1
    toolbox_root = toolbox_root or context.toolbox_root
    result = run_python_plan(
        code_body,
        user_id=context.user_id,
        toolbox_root=toolbox_root,
        timeout_sec=timeout_sec,
        run_id=context.run_id,
    )
    normalized_label = (label or "sandbox").strip() or "sandbox"
    context.record_event(
        "mcp.sandbox.run",
        {
            "success": result.success,
            "timed_out": result.timed_out,
            "log_lines": len(result.logs),
            "code_preview": code_body[:200],
            "label": normalized_label,
        },
    )
    normalized_result = unwrap_nested_data(result.result)
    entry = {
        "type": "sandbox",
        "label": normalized_label,
        "success": result.success,
        "timed_out": result.timed_out,
        "logs": result.logs,
        "error": result.error,
        "result": normalized_result,
        "code_preview": code_body[:1200],
    }
    key = f"sandbox.{normalized_label}"
    context.append_raw_output(key, entry)
    if normalized_result is not None:
        summary = context.summarize_sandbox_output(normalized_label, normalized_result)
        if summary:
            entry["summary"] = summary
    return SandboxExecutionResult(result=result, code_body=code_body)
