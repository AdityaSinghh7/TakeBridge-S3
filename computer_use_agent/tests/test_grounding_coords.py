from pathlib import Path
import sys
import base64

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from computer_use_agent.grounding.grounding_agent import (
    _decode_screenshot_data,
    _normalize_point_to_dims,
    _parse_xy_from_text,
)


def test_parse_xy_from_text_click_floats():
    point = _parse_xy_from_text("click(0.47, 0.62)")
    assert point is not None
    x, y = point
    assert abs(x - 0.47) < 1e-6
    assert abs(y - 0.62) < 1e-6


def test_parse_xy_from_text_bracket():
    point = _parse_xy_from_text("[512.3, 384.8]")
    assert point is not None
    x, y = point
    assert abs(x - 512.3) < 1e-6
    assert abs(y - 384.8) < 1e-6


def test_normalize_point_norm1_to_target_dims():
    coords = _normalize_point_to_dims(
        0.5,
        0.25,
        img_w=1920,
        img_h=1080,
        target_w=1920,
        target_h=1080,
        allow_norm_1000=True,
    )
    assert coords == [960, 270]


def test_normalize_point_norm1000_to_target_dims():
    coords = _normalize_point_to_dims(
        500.0,
        250.0,
        img_w=1920,
        img_h=1080,
        target_w=1920,
        target_h=1080,
        allow_norm_1000=True,
    )
    assert coords == [960, 270]


def test_normalize_point_pixels_to_target_dims():
    coords = _normalize_point_to_dims(
        960.0,
        270.0,
        img_w=1920,
        img_h=1080,
        target_w=1920,
        target_h=1080,
        allow_norm_1000=False,
    )
    assert coords == [960, 270]


def test_normalize_point_auto_prefers_pixels_for_large_images():
    coords = _normalize_point_to_dims(
        500.0,
        250.0,
        img_w=1920,
        img_h=1080,
        target_w=1920,
        target_h=1080,
        allow_norm_1000=None,
    )
    assert coords == [500, 250]


def test_decode_screenshot_data_strips_data_url():
    raw = b"hello"
    b64 = base64.b64encode(raw).decode("utf-8")
    data_url = f"data:image/png;base64,{b64}"
    assert _decode_screenshot_data(data_url) == raw
