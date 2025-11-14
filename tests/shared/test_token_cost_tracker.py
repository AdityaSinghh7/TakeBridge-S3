from __future__ import annotations

import json
from pathlib import Path

from shared.token_cost_tracker import TOKEN_TRACKER, TokenCostTracker


class DummyResponse:
    def __init__(self, input_tokens: int, cached_tokens: int, output_tokens: int) -> None:
        self.usage = {
            "input_tokens": input_tokens,
            "input_cached_tokens": cached_tokens,
            "output_tokens": output_tokens,
        }


def test_token_cost_tracker_records_usage_and_summary(tmp_path: Path) -> None:
    tracker = TokenCostTracker()
    tracker.logs_dir = tmp_path
    tracker.log_path = tmp_path / "token-costs.jsonl"

    tracker.record_response("o4-mini", "unit-test", DummyResponse(10, 2, 4))

    assert tracker.total_input_cached == 2
    assert tracker.total_input_new == 8
    assert tracker.total_output == 4
    assert tracker.total_cost_usd > 0

    tracker.write_summary()
    tracker.write_summary()  # summary is only written once

    log_lines = tracker.log_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(log_lines) == 2
    first, second = map(json.loads, log_lines)
    assert first["type"] == "call"
    assert second["type"] == "summary"


def test_shared_token_tracker_initialized_under_logs_dir() -> None:
    assert isinstance(TOKEN_TRACKER, TokenCostTracker)
    assert TOKEN_TRACKER.log_path.parent == Path("logs")
