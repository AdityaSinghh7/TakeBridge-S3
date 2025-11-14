from __future__ import annotations

import pytest

pytest.importorskip("openai")

from shared.oai_client import ResponseSession, extract_assistant_text


class DummyResponse:
    def __init__(self, output):
        self.output = output
        self.id = "resp-123"


def test_extract_assistant_text_concatenates_output_text() -> None:
    response = DummyResponse(
        [
            {
                "type": "message",
                "role": "assistant",
                "content": [
                    {"type": "output_text", "text": "Hello"},
                    {"type": "output_text", "text": " World"},
                ],
            }
        ]
    )
    assert extract_assistant_text(response) == "Hello World"


def test_response_session_tracks_previous_response_and_carry_items() -> None:
    response = DummyResponse(
        [
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": "Hi"}],
            },
            {
                "type": "reasoning",
                "content": [{"type": "output_text", "text": "Chain"}],
            },
        ]
    )
    session = ResponseSession()
    session.update_from(response)

    assert session.previous_response_id == "resp-123"
    assert session.carry_items
