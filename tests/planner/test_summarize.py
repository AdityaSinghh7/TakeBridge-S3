from __future__ import annotations

import json
from pathlib import Path

from mcp_agent.planner.summarize import redact_payload, summarize_payload
from mcp_agent.planner.context import PlannerContext
from mcp_agent.planner.budget import Budget


def test_summarize_payload_truncates_and_persists(tmp_path: Path):
    payload = [{"token": f"secret-{i}", "value": i} for i in range(5)]
    summary = summarize_payload(
        "gmail_search",
        payload,
        purpose="for_planning",
        max_chars=20,
        storage_dir=tmp_path,
        persist_payload=True,
    )

    assert summary["label"] == "gmail_search"
    assert summary["truncated"] is True
    assert summary["schema"]["type"] == "list[object]"
    assert summary["aggregates"]["count"] == 5
    assert all(item["token"] == "[REDACTED]" for item in summary["sample"])
    assert summary["storage_ref"].endswith("gmail_search.json")
    assert (tmp_path / "gmail_search.json").exists()


def test_redact_payload_masks_nested_keys():
    payload = {"Authorization": "Bearer 123", "nested": {"api_key": "456", "value": 1}}
    redacted = redact_payload(payload)
    assert redacted["Authorization"] == "[REDACTED]"
    assert redacted["nested"]["api_key"] == "[REDACTED]"
    assert redacted["nested"]["value"] == 1


def test_context_should_summarize_threshold(tmp_path: Path):
    context = PlannerContext(task="demo", user_id="tester", budget=Budget())
    big_payload = [{"value": i} for i in range(200)]
    assert context.should_summarize(big_payload) is True
    small_payload = {"value": 1}
    assert context.should_summarize(small_payload) is False


def test_summarize_payload_large_payload_auto_persists_and_redacts(tmp_path: Path):
    payload = [{"token": f"secret-{i}", "value": i} for i in range(300)]
    summary = summarize_payload("large_payload", payload, storage_dir=tmp_path)

    assert summary["truncated"] is True
    assert summary["aggregates"]["count"] == len(payload)
    assert "storage_ref" in summary
    stored_path = Path(summary["storage_ref"])
    assert stored_path.exists()
    stored_payload = json.loads(stored_path.read_text())
    assert stored_payload[0]["token"] == "[REDACTED]"
    assert stored_payload[0]["value"] == 0
