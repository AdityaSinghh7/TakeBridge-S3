from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from mcp_agent.execution.envelope import unwrap_nested_data

from .context import PlannerContext

SENTINEL = "___TB_RESULT___"


@dataclass
class SandboxResult:
    """Result of sandbox code execution."""
    success: bool
    result: Optional[Dict[str, Any]]
    logs: List[str]
    error: Optional[str]
    timed_out: bool


@dataclass
class SandboxExecutionResult:
    result: SandboxResult
    code_body: str


def _build_plan_source(code_body: str) -> str:
    """Build complete Python source for sandbox execution."""
    return textwrap.dedent(f"""
        from __future__ import annotations
        import sys
        import json
        from mcp_agent.sandbox.glue import register_default_tool_caller
        
        SENTINEL = {SENTINEL!r}
        
        def plan():
        {textwrap.indent(code_body, "    ")}
        
        if __name__ == "__main__":
            register_default_tool_caller()
            try:
                result = plan()
                print(SENTINEL, flush=True)
                json.dump({{"result": result}}, sys.stdout, ensure_ascii=False, default=str)
                print(flush=True)
            except Exception as exc:
                print(SENTINEL, flush=True)
                json.dump({{"error": str(exc)}}, sys.stdout, ensure_ascii=False, default=str)
                print(flush=True)
                raise
    """)


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
    toolbox_root_path = toolbox_root or context.toolbox_root
    
    # Execute sandbox
    from mcp_agent.env_sync import ensure_env_for_provider
    for provider in ("gmail", "slack"):
        ensure_env_for_provider(context.user_id, provider)
    
    python_cmd = sys.executable
    if not python_cmd:
        raise RuntimeError("Unable to determine python executable for sandbox run.")
    
    plan_source = _build_plan_source(code_body or "    pass")
    repo_root = Path(__file__).resolve().parents[2]
    
    with tempfile.TemporaryDirectory(prefix=f"sandbox-{context.user_id}-") as tmpdir:
        tmp_path = Path(tmpdir)
        plan_path = tmp_path / "plan.py"
        plan_path.write_text(plan_source, encoding="utf-8")
        
        env = os.environ.copy()
        existing_pythonpath = env.get("PYTHONPATH", "")
        path_entries = [toolbox_root_path, repo_root]
        if existing_pythonpath:
            path_entries.append(existing_pythonpath)
        env["PYTHONPATH"] = os.pathsep.join(str(p) for p in path_entries if p)
        env["TB_USER_ID"] = context.user_id
        env["TB_REQUEST_ID"] = context.run_id
        
        try:
            completed = subprocess.run(
                [python_cmd, str(plan_path)],
                cwd=tmp_path,
                capture_output=True,
                text=True,
                timeout=timeout_sec,
                env=env,
                check=False,
            )
            timed_out = False
        except subprocess.TimeoutExpired as exc:
            stdout_text = exc.stdout.decode("utf-8") if exc.stdout else ""
            stderr_text = exc.stderr.decode("utf-8") if exc.stderr else ""
            result = SandboxResult(
                success=False,
                result=None,
                logs=[stdout_text, stderr_text],
                error=f"Timeout after {timeout_sec}s",
                timed_out=True,
            )
            normalized_label = (label or "sandbox").strip() or "sandbox"
            context.record_event(
                "mcp.sandbox.run",
                {
                    "success": False,
                    "timed_out": True,
                    "log_lines": 2,
                    "code_preview": code_body[:200],
                    "label": normalized_label,
                },
            )
            return SandboxExecutionResult(result=result, code_body=code_body)
        
        # Parse output
        stdout = completed.stdout or ""
        stderr = completed.stderr or ""
        logs = [line for line in (stdout + "\n" + stderr).splitlines() if line.strip()]
        
        if SENTINEL in stdout:
            sentinel_idx = stdout.index(SENTINEL)
            json_start = sentinel_idx + len(SENTINEL)
            json_str = stdout[json_start:].strip()
            try:
                parsed = json.loads(json_str)
                if "error" in parsed:
                    result = SandboxResult(
                        success=False,
                        result=None,
                        logs=logs,
                        error=parsed["error"],
                        timed_out=False,
                    )
                else:
                    result = SandboxResult(
                        success=True,
                        result=parsed.get("result"),
                        logs=logs,
                        error=None,
                        timed_out=False,
                    )
            except json.JSONDecodeError:
                result = SandboxResult(
                    success=False,
                    result=None,
                    logs=logs,
                    error="Failed to parse sandbox output",
                    timed_out=False,
                )
        else:
            error_msg = stderr or "Sandbox execution failed (no sentinel found)"
            result = SandboxResult(
                success=False,
                result=None,
                logs=logs,
                error=error_msg,
                timed_out=False,
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
