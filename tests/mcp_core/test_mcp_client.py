from __future__ import annotations

import pytest

from mcp_agent.mcp_client import MCPClient


def test_mcp_client_acall_delegates(monkeypatch: pytest.MonkeyPatch) -> None:
    client = MCPClient("https://example.com")

    async def fake_async_call(self, tool: str, args: dict):
        return {"tool": tool, "args": args}

    monkeypatch.setattr(MCPClient, "_acall", fake_async_call)

    import asyncio

    result = asyncio.run(client.acall("demo", {"value": 1}))
    assert result == {"tool": "demo", "args": {"value": 1}}
