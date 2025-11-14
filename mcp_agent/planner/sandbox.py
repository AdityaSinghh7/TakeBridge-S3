from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

from mcp_agent.sandbox.runner import SandboxResult, run_python_plan

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
    context.budget_tracker.code_runs += 1
    toolbox_root = toolbox_root or context.toolbox_root
    result = run_python_plan(
        code_body,
        user_id=context.user_id,
        toolbox_root=toolbox_root,
        timeout_sec=timeout_sec,
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
    context.raw_outputs[f"sandbox.{normalized_label}"] = {
        "type": "sandbox",
        "label": normalized_label,
        "success": result.success,
        "timed_out": result.timed_out,
        "logs": result.logs,
        "error": result.error,
        "result": result.result,
        "code_preview": code_body[:1200],
    }
    if result.result is not None:
        context.summarize_sandbox_output(normalized_label, result.result)
    return SandboxExecutionResult(result=result, code_body=code_body)
