from __future__ import annotations

import json
from typing import Any, Dict, List, Tuple

import pytest

import mcp_agent.actions as actions

TEST_USER = "test-user"


@pytest.fixture(autouse=True)
def _set_user(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("TB_USER_ID", TEST_USER)


class DummyAgent:
    def __init__(self) -> None:
        self.calls: List[Tuple[str, str, Dict[str, Any]]] = []

    def call_tool(self, provider: str, tool: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        self.calls.append((provider, tool, payload))
        return {"successful": True, "data": {"ok": True}}


def _patch_agent(monkeypatch: pytest.MonkeyPatch) -> DummyAgent:
    agent = DummyAgent()

    def fake_current(cls, user_id):
        return agent

    monkeypatch.setattr(actions.MCPAgent, "current", classmethod(fake_current))
    return agent


def _patch_authorization(monkeypatch: pytest.MonkeyPatch, allowed: Dict[str, bool]) -> None:
    def fake_is_authorized(cls, provider: str, user_id: str) -> bool:
        return allowed.get(provider, False)

    monkeypatch.setattr(actions.OAuthManager, "is_authorized", classmethod(fake_is_authorized))


def _capture_events(monkeypatch: pytest.MonkeyPatch) -> List[Tuple[str, Dict[str, Any]]]:
    events: List[Tuple[str, Dict[str, Any]]] = []

    def fake_emit(event: str, data: Dict[str, Any]) -> None:
        events.append((event, data))

    monkeypatch.setattr(actions, "emit_event", fake_emit)
    return events


def test_slack_post_message_calls_mcp_with_telemetry(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_authorization(monkeypatch, {"slack": True})
    agent = _patch_agent(monkeypatch)
    events = _capture_events(monkeypatch)

    result = actions.slack_post_message(
        object(),
        "#general",
        text="hello",
        blocks={"type": "section", "text": "sample"},
    )

    assert result["successful"] is True
    assert result["provider"] == "slack"
    assert result["tool"] == "SLACK_SEND_MESSAGE"
    assert result["payload_keys"] == ["blocks", "channel", "text"]
    assert result["data"] == {"ok": True}
    assert agent.calls == [
        (
            "slack",
            "SLACK_SEND_MESSAGE",
            {
                "channel": "#general",
                "text": "hello",
                "blocks": json.dumps({"type": "section", "text": "sample"}),
            },
        )
    ]
    event_names = [name for name, _ in events]
    assert "mcp.action.started" in event_names
    assert "mcp.action.completed" in event_names


def test_gmail_send_email_requires_auth_and_logs_skip(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_authorization(monkeypatch, {"gmail": False})
    events = _capture_events(monkeypatch)

    result = actions.gmail_send_email(object(), "a@example.com", "Subject", "Body")

    assert result["successful"] is False
    assert result["error"] == "unauthorized"
    assert result["provider"] == "gmail"
    assert result["tool"] == "GMAIL_SEND_EMAIL"
    assert (
        "mcp.call.skipped",
        {"server": "gmail", "tool": "GMAIL_SEND_EMAIL", "reason": "unauthorized", "user_id": TEST_USER},
    ) in events


def test_gmail_recipient_normalization(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_authorization(monkeypatch, {"gmail": True})
    agent = _patch_agent(monkeypatch)
    _capture_events(monkeypatch)

    actions.gmail_send_email(
        object(),
        "primary@example.com,extra@example.com",
        "Subject",
        "Body",
        cc="cc1@example.com",
        bcc="bcc1@example.com, bcc2@example.com",
        is_html=True,
    )

    assert len(agent.calls) == 1
    _, _, payload = agent.calls[0]
    assert payload["recipient_email"] == "primary@example.com"
    # Secondary TO should flow into CC list
    assert "extra@example.com" in payload["cc"]
    assert payload["bcc"] == ["bcc1@example.com", "bcc2@example.com"]
    assert payload["is_html"] is True


def test_gmail_search_uses_gmail_user_id_not_tb_user(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    gmail_search should pass the Gmail API userId (typically 'me')
    through to the MCP payload, and must not overwrite it with the
    TB user id used for MCPAgent selection.
    """
    _patch_authorization(monkeypatch, {"gmail": True})
    agent = _patch_agent(monkeypatch)
    _capture_events(monkeypatch)

    # Pass an explicit Gmail user_id; this should flow through to the payload.
    actions.gmail_search(object(), "in:inbox", max_results=3, user_id="me")

    assert len(agent.calls) == 1
    provider, tool, payload = agent.calls[0]
    assert provider == "gmail"
    assert tool == "GMAIL_FETCH_EMAILS"
    # Gmail API userId should be 'me', never the TB user id.
    assert payload["user_id"] == "me"
