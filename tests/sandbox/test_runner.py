from __future__ import annotations

from pathlib import Path

import pytest

from mcp_agent.sandbox.runner import run_python_plan, SandboxResult


@pytest.fixture(autouse=True)
def disable_default_caller(monkeypatch):
    monkeypatch.setenv("TB_DISABLE_SANDBOX_CALLER", "1")


@pytest.fixture()
def toolbox_root(tmp_path: Path) -> Path:
    sandbox_pkg = tmp_path / "sandbox_py"
    servers_pkg = sandbox_pkg / "servers"
    servers_pkg.mkdir(parents=True, exist_ok=True)
    (sandbox_pkg / "__init__.py").write_text(
        "from . import servers\n__all__ = ['servers']\n",
        encoding="utf-8",
    )
    (sandbox_pkg / "client.py").write_text(
        "from typing import Any, Awaitable, Callable, Dict\n\n"
        "ToolCallResult = Dict[str, Any]\n"
        "ToolCaller = Callable[[str, str, Dict[str, Any]], Awaitable[ToolCallResult]]\n"
        "def register_tool_caller(caller: ToolCaller) -> None:\n"
        "    pass\n"
        "async def call_tool(provider: str, tool: str, payload: Dict[str, Any], **kwargs) -> ToolCallResult:\n"
        "    return {'provider': provider, 'tool': tool, 'payload': payload}\n",
        encoding="utf-8",
    )
    (servers_pkg / "__init__.py").write_text("", encoding="utf-8")
    return tmp_path


def test_run_python_plan_success(toolbox_root: Path):
    code_body = "return {'status': 'ok', 'items': [1, 2, 3]}"
    result = run_python_plan(code_body, user_id="tester", toolbox_root=toolbox_root, timeout_sec=5)

    assert isinstance(result, SandboxResult)
    assert result.success is True
    assert result.result == {"status": "ok", "items": [1, 2, 3]}
    assert result.error is None
    assert result.timed_out is False


def test_run_python_plan_failure(toolbox_root: Path):
    code_body = "raise RuntimeError('boom')"
    result = run_python_plan(code_body, user_id="tester", toolbox_root=toolbox_root, timeout_sec=5)

    assert result.success is False
    assert result.result is None
    assert "boom" in "\n".join(result.logs)
    assert result.error is not None
    assert result.timed_out is False


def test_run_python_plan_timeout(toolbox_root: Path):
    code_body = """
import asyncio
await asyncio.sleep(2)
return {'status': 'slow'}
"""
    result = run_python_plan(code_body, user_id="tester", toolbox_root=toolbox_root, timeout_sec=0.1)

    assert result.success is False
    assert result.timed_out is True
    assert result.error == "sandbox timed out after 0.1s"


def test_run_python_plan_scopes_tb_user_id(toolbox_root: Path):
    code_body = """
import os
return {'user': os.getenv('TB_USER_ID')}
"""
    alpha = run_python_plan(code_body, user_id="alpha-user", toolbox_root=toolbox_root, timeout_sec=5)
    beta = run_python_plan(code_body, user_id="beta-user", toolbox_root=toolbox_root, timeout_sec=5)

    assert alpha.success is True
    assert beta.success is True
    assert alpha.result == {"user": "alpha-user"}
    assert beta.result == {"user": "beta-user"}
