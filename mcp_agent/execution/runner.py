"""Python sandbox execution for MCP agent (migrated from sandbox/runner.py).

Runs generated Python code in isolated subprocess with MCP tool access.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from mcp_agent.core.context import AgentContext

SENTINEL = "___TB_RESULT___"


@dataclass
class SandboxResult:
    """Result of sandbox code execution."""
    success: bool
    result: Optional[Dict[str, Any]]
    logs: List[str]
    error: Optional[str]
    timed_out: bool


def run_python_plan(
    context: AgentContext,
    code_body: str,
    *,
    timeout_sec: int = 30,
    python_executable: str | None = None,
    label: str = "sandbox",
) -> SandboxResult:
    """
    Execute generated Python code in a subprocess sandbox.
    
    The sandbox has access to MCP tools via the injected context.
    
    Args:
        context: Agent context with user_id
        code_body: Python code to execute (function body, no signature)
        timeout_sec: Execution timeout in seconds
        python_executable: Optional python path override
        label: Label for logging
    
    Returns:
        SandboxResult with success, result, logs, and error
    """
    python_cmd = python_executable or sys.executable
    if not python_cmd:
        raise RuntimeError("Unable to determine python executable for sandbox run.")
    
    # Ensure environment for providers
    from mcp_agent.actions import SUPPORTED_PROVIDERS
    from mcp_agent.env_sync import ensure_env_for_provider
    for provider in SUPPORTED_PROVIDERS:
        ensure_env_for_provider(context.user_id, provider)
    
    # Build plan source
    plan_source = _build_plan_source(code_body or "    pass")
    
    repo_root = Path(__file__).resolve().parents[2]

    debug_dir = os.getenv("TB_SANDBOX_DEBUG_DIR")
    with tempfile.TemporaryDirectory(prefix=f"sandbox-{context.user_id}-") as tmpdir:
        tmp_path = Path(tmpdir)
        plan_path = tmp_path / "plan.py"
        plan_path.write_text(plan_source, encoding="utf-8")

        if debug_dir:
            debug_path = Path(debug_dir).expanduser().resolve()
            debug_path.mkdir(parents=True, exist_ok=True)
            snapshot = debug_path / f"plan_{context.user_id}_{label}.py"
            snapshot.write_text(plan_source, encoding="utf-8")

        env = os.environ.copy()
        existing_pythonpath = env.get("PYTHONPATH", "")
        path_entries = []
        toolbox_root = (context.extra or {}).get("toolbox_root")
        if toolbox_root:
            path_entries.append(str(toolbox_root))
        path_entries.append(str(repo_root))
        if existing_pythonpath:
            path_entries.append(existing_pythonpath)
        env["PYTHONPATH"] = os.pathsep.join(value for value in path_entries if value)
        env["TB_USER_ID"] = context.user_id
        env["TB_REQUEST_ID"] = context.request_id
        
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
        except subprocess.TimeoutExpired as exc:
            return SandboxResult(
                success=False,
                result=None,
                logs=_collect_logs(exc.stdout, exc.stderr),
                error=f"sandbox timed out after {timeout_sec}s",
                timed_out=True,
            )
    
    stdout = completed.stdout or ""
    stderr = completed.stderr or ""
    logs, parsed_result = _parse_process_output(stdout)
    stderr_lines = [line for line in stderr.splitlines() if line]
    logs.extend(stderr_lines)
    
    success = completed.returncode == 0 and parsed_result is not None
    error: Optional[str] = None
    if not success:
        detail = stderr_lines[0] if stderr_lines else (logs[0] if logs else "")
        base = (
            f"sandbox exited with code {completed.returncode}"
            if completed.returncode
            else "sandbox produced no result"
        )
        if detail:
            detail = detail.strip()
            error = f"{base}: {detail[:200]}"
        else:
            error = base
    
    return SandboxResult(
        success=success,
        result=parsed_result,
        logs=logs,
        error=error,
        timed_out=False,
    )


def _build_plan_source(code_body: str) -> str:
    """Build complete Python source for sandbox execution."""
    indented = textwrap.indent(code_body.rstrip() + "\n", "    ")
    template = """\
import asyncio
import json
import os
import sys
import traceback

class _SandboxNullWriter:
    def write(self, _):
        pass

    def flush(self):
        pass


_ORIGINAL_STDOUT = sys.stdout
_ORIGINAL_STDERR = sys.stderr
sys.stdout = _SandboxNullWriter()
sys.stderr = _SandboxNullWriter()
from sandbox_py.helpers import safe_error_text, safe_timestamp_sort_key
from mcp_agent.sandbox.runtime import call_tool  # noqa: F401
from mcp_agent.sandbox.glue import register_default_tool_caller
from mcp_agent.core.context import AgentContext

SENTINEL = "{sentinel}"

register_default_tool_caller()

# Create context from environment variables
context = AgentContext.create(
    user_id=os.getenv("TB_USER_ID", "dev-local"),
    request_id=os.getenv("TB_REQUEST_ID", ""),
)



async def main():
{body}


def _emit_result(payload):
    sys.stdout = _ORIGINAL_STDOUT
    sys.stderr = _ORIGINAL_STDERR
    sys.stdout.write(SENTINEL + json.dumps(payload or {{}}, default=str))
    sys.stdout.flush()


if __name__ == "__main__":
    try:
        result = asyncio.run(main())
    except Exception as exc:  # pragma: no cover - sandbox error surfacing
        error_payload = {{
            "successful": False,
            "error": "Sandbox error: " + str(exc),
            "traceback": traceback.format_exc(),
            "data": {{}},
        }}
        _emit_result(error_payload)
    else:
        _emit_result(result)
"""
    return textwrap.dedent(template).format(sentinel=SENTINEL, body=indented)


def _parse_process_output(stdout: str) -> tuple[List[str], Optional[Dict[str, Any]]]:
    """Parse sandbox output to extract logs and result."""
    if SENTINEL not in stdout:
        return [line for line in stdout.splitlines() if line], None
    
    pre, _, post = stdout.partition(SENTINEL)
    logs = [line for line in pre.splitlines() if line]
    json_text = post.strip()
    
    try:
        result = json.loads(json_text) if json_text else {}
    except json.JSONDecodeError:
        from json import JSONDecoder
        try:
            result, _ = JSONDecoder().raw_decode(json_text)
        except json.JSONDecodeError:
            logs.append("Failed to parse sandbox result JSON.")
            return logs, None
    
    return logs, result or {}


def _collect_logs(stdout: Optional[str], stderr: Optional[str]) -> List[str]:
    """Collect logs from stdout and stderr."""
    logs: List[str] = []
    if stdout:
        logs.extend(stdout.splitlines())
    if stderr:
        logs.extend(stderr.splitlines())
    return logs
