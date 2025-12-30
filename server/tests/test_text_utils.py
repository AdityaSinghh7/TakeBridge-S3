from __future__ import annotations

from shared.text_utils import safe_ascii, safe_utf8


def test_safe_ascii_escapes_non_ascii():
    value = "Refund policy: >3 refunds in 90 days \\u2192 manual review"
    assert safe_ascii(value) == value
    assert safe_ascii("x\u2192y") == "x\\u2192y"


def test_safe_utf8_handles_bytes():
    assert safe_utf8(b"hello") == "hello"
    assert safe_utf8("hello") == "hello"
