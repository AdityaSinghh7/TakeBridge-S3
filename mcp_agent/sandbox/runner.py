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

from mcp_agent.env_sync import ensure_env_for_provider

SENTINEL = "___TB_RESULT___"


@dataclass
class SandboxResult:
    success: bool
    result: Optional[Dict[str, Any]]
    logs: List[str]
    error: Optional[str]
    timed_out: bool


def run_python_plan(
    code_body: str,
    *,
    user_id: str,
    toolbox_root: Path,
    timeout_sec: int = 30,
    python_executable: str | None = None,
) -> SandboxResult:
    """
    Execute generated sandbox Python code inside a temporary working directory.

    Args:
        code_body: Body of the async function the model authored (no signature).
        user_id: Current user identifier (used for telemetry/logging paths).
        toolbox_root: Root directory containing sandbox_py package.
        timeout_sec: Hard timeout for the subprocess execution.
        python_executable: Optional python path override (defaults to sys.executable).
    """

    python_cmd = python_executable or sys.executable
    if not python_cmd:
        raise RuntimeError("Unable to determine python executable for sandbox run.")

    toolbox_root = Path(toolbox_root).resolve()
    if not toolbox_root.exists():
        raise FileNotFoundError(f"toolbox_root does not exist: {toolbox_root}")

    for provider in ("gmail", "slack"):
        ensure_env_for_provider(user_id, provider)

    plan_source = _build_plan_source(code_body or "    pass")

    repo_root = Path(__file__).resolve().parents[2]

    with tempfile.TemporaryDirectory(prefix=f"sandbox-{user_id}-") as tmpdir:
        tmp_path = Path(tmpdir)
        plan_path = tmp_path / "plan.py"
        plan_path.write_text(plan_source, encoding="utf-8")

        env = os.environ.copy()
        existing_pythonpath = env.get("PYTHONPATH", "")
        path_entries = [toolbox_root, repo_root]
        if existing_pythonpath:
            path_entries.append(existing_pythonpath)
        env["PYTHONPATH"] = os.pathsep.join(str(value) for value in path_entries if value)
        env["TB_USER_ID"] = user_id

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
    indented = textwrap.indent(code_body.rstrip() + "\n", "    ")
    template = f"""\
import asyncio
import json
from sandbox_py import servers  # noqa: F401
from mcp_agent.sandbox.glue import register_default_tool_caller

register_default_tool_caller()


async def main():
{indented}


if __name__ == "__main__":
    result = asyncio.run(main())
    print("{SENTINEL}" + json.dumps(result or {{}}))
"""
    return textwrap.dedent(template)


def _parse_process_output(stdout: str) -> tuple[List[str], Optional[Dict[str, Any]]]:
    if SENTINEL not in stdout:
        return [line for line in stdout.splitlines() if line], None
    pre, _, post = stdout.partition(SENTINEL)
    logs = [line for line in pre.splitlines() if line]
    json_text = post.strip()
    try:
        result = json.loads(json_text) if json_text else {}
    except json.JSONDecodeError:
        logs.append("Failed to parse sandbox result JSON.")
        return logs, None
    return logs, result or {}


def _collect_logs(stdout: Optional[str], stderr: Optional[str]) -> List[str]:
    logs: List[str] = []
    if stdout:
        logs.extend(stdout.splitlines())
    if stderr:
        logs.extend(stderr.splitlines())
    return logs
