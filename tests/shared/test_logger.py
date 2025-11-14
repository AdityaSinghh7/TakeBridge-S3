from __future__ import annotations

import logging

import pytest

from shared.logger import StructuredLogger


def test_structured_logger_emits_header_and_lines(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO)
    logger = StructuredLogger("shared.tests.logger")
    logger.info_lines("Header", ["First", "Second"])

    records = [rec.message for rec in caplog.records]
    assert "Header" in records
    assert "  First" in records
    assert "  Second" in records
