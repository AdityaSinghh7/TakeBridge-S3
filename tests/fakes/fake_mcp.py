from __future__ import annotations

from typing import Any, Dict, List


CALL_HISTORY: List[Dict[str, Any]] = []


class StubMCPClient:
    def __init__(self, provider: str):
        self.provider = provider
        self.base_url = f"https://fake/{provider}"
        self.headers: Dict[str, str] = {}

    def call(self, tool: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        CALL_HISTORY.append({"provider": self.provider, "tool": tool, "payload": payload})
        return {
            "successful": True,
            "data": {
                "provider": self.provider,
                "tool": tool,
                "echo": payload,
            },
            "logs": [f"{self.provider}.{tool} invoked"],
        }

    def list_tools(self) -> List[str]:
        return []


def reset_history() -> None:
    CALL_HISTORY.clear()


def build_fake_clients(user_id: str | None = None) -> Dict[str, StubMCPClient]:
    """Factory used by tests via MCP_FAKE_CLIENT_FACTORY env var."""
    reset_history()
    return {
        "slack": StubMCPClient("slack"),
        "gmail": StubMCPClient("gmail"),
    }
