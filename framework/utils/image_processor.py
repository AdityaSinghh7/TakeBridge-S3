"""
Reusable image processing utilities for the agentic framework.

Provides a lightweight `ImageProcessor` facade plus module-level helpers
for common encoding, resizing, and annotation tasks.
"""

from __future__ import annotations

import base64
import math
from io import BytesIO
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import cv2  # type: ignore
import numpy as np


class ImageProcessor:
    """
    Convenience wrapper around common image-processing primitives used across
    the framework. Exposes stateless helpers as `@staticmethod`s alongside
    messaging utilities that utilise configurable content keys.
    """

    def __init__(self, *, image_key: str = "image_url", text_key: str = "text") -> None:
        self.image_key = image_key
        self.text_key = text_key

    # ------------------------------------------------------------------ #
    # Encoding helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def encode_numpy_image_to_base64(image: np.ndarray) -> str:
        success, buffer = cv2.imencode(".png", image)
        if not success:
            raise ValueError("Failed to encode image to png format")
        return base64.b64encode(buffer.tobytes()).decode("utf-8")

    @staticmethod
    def encode_image_bytes(image_content: bytes) -> str:
        return base64.b64encode(image_content).decode("utf-8")

    def encode_image(self, image_content: bytes) -> str:
        return self.encode_image_bytes(image_content)

    @staticmethod
    def downscale_image_bytes(image: bytes, max_w: int = 1280, max_h: int = 720) -> bytes:
        np_img = np.frombuffer(image, dtype=np.uint8)
        img = cv2.imdecode(np_img, cv2.IMREAD_COLOR)
        if img is None:
            return image
        height, width = img.shape[:2]
        scale = min(max_w / float(width), max_h / float(height), 1.0)
        if scale < 1.0:
            new_w = max(int(width * scale), 1)
            new_h = max(int(height * scale), 1)
            img = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)
        ok, buf = cv2.imencode(".png", img)
        if not ok:
            return image
        return buf.tobytes()

    # ------------------------------------------------------------------ #
    # Message formatting
    # ------------------------------------------------------------------ #

    def format_image(self, image: bytes, detail: str = "high") -> Dict[str, Any]:
        return {
            "type": self.image_key,
            "image_url": f"data:image/png;base64,{self.encode_image(image)}",
            "detail": detail,
        }

    def format_text_message(self, text: str) -> Dict[str, Any]:
        return {"type": self.text_key, "text": text}

    def create_system_message(self, content: str) -> Dict[str, Any]:
        return {"role": "system", "content": [self.format_text_message(content)]}

    def create_user_message(
        self,
        *,
        text: Optional[str] = None,
        image: Optional[bytes] = None,
        detail: str = "high",
        image_first: bool = False,
    ) -> Dict[str, Any]:
        if text is None and image is None:
            raise ValueError("At least one of text or image must be provided")

        content: List[Dict[str, Any]] = []
        if text is not None:
            content.append(self.format_text_message(text))
        if image is not None:
            content.append(self.format_image(image, detail=detail))
        if image_first:
            content.reverse()
        return {"role": "user", "content": content}

    def create_assistant_message(self, text: str) -> Dict[str, Any]:
        return {"role": "assistant", "content": [{"type": "output_text", "text": text}]}

    # ------------------------------------------------------------------ #
    # Hashing / fingerprinting
    # ------------------------------------------------------------------ #

    @staticmethod
    def dhash(image_bytes: bytes, hash_size: int = 8) -> int:
        try:
            from PIL import Image  # Pillow may be optional
        except Exception:
            return 0

        try:
            img = (
                Image.open(BytesIO(image_bytes))
                .convert("L")
                .resize((hash_size + 1, hash_size), Image.LANCZOS)
            )
            pixels = np.asarray(img)
            diff = pixels[:, 1:] > pixels[:, :-1]
            value = 0
            for bit in diff.flatten():
                value = (value << 1) | int(bit)
            return value
        except Exception:
            return 0

    # ------------------------------------------------------------------ #
    # Geometry helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def round_by_factor(number: int, factor: int) -> int:
        return round(number / factor) * factor

    @staticmethod
    def ceil_by_factor(number: int, factor: int) -> int:
        return math.ceil(number / factor) * factor

    @staticmethod
    def floor_by_factor(number: int, factor: int) -> int:
        return math.floor(number / factor) * factor

    @classmethod
    def smart_resize(
        cls,
        height: int,
        width: int,
        *,
        factor: int = 28,
        min_pixels: int = 56 * 56,
        max_pixels: int = 14 * 14 * 4 * 1280,
        max_long_side: int = 8192,
    ) -> Tuple[int, int]:
        if height < 2 or width < 2:
            raise ValueError(f"height:{height} or width:{width} must be larger than factor:{factor}")
        if max(height, width) / min(height, width) > 200:
            raise ValueError(
                f"absolute aspect ratio must be smaller than 100, got {height} / {width}"
            )

        if max(height, width) > max_long_side:
            beta = max(height, width) / max_long_side
            height = int(height / beta)
            width = int(width / beta)

        h_bar = cls.round_by_factor(height, factor)
        w_bar = cls.round_by_factor(width, factor)
        if h_bar * w_bar > max_pixels:
            beta = math.sqrt((height * width) / max_pixels)
            h_bar = cls.floor_by_factor(height / beta, factor)
            w_bar = cls.floor_by_factor(width / beta, factor)
        elif h_bar * w_bar < min_pixels:
            beta = math.sqrt(min_pixels / (height * width))
            h_bar = cls.ceil_by_factor(height * beta, factor)
            w_bar = cls.ceil_by_factor(width * beta, factor)
        return int(h_bar), int(w_bar)

    @classmethod
    def update_image_size(
        cls,
        image_ele: Dict[str, Any],
        *,
        min_tokens: int = 1,
        max_tokens: int = 12800,
        merge_base: int = 2,
        patch_size: int = 14,
    ) -> Dict[str, Any]:
        height, width = image_ele["height"], image_ele["width"]
        pixels_per_token = patch_size * patch_size * merge_base * merge_base
        resized_height, resized_width = cls.smart_resize(
            height,
            width,
            factor=merge_base * patch_size,
            min_pixels=pixels_per_token * min_tokens,
            max_pixels=pixels_per_token * max_tokens,
            max_long_side=50000,
        )
        image_ele.update(
            {
                "resized_height": resized_height,
                "resized_width": resized_width,
                "seq_len": resized_height * resized_width // pixels_per_token + 2,
            }
        )
        return image_ele

    # ------------------------------------------------------------------ #
    # Bounding boxes / points conversion
    # ------------------------------------------------------------------ #

    @staticmethod
    def _convert_bbox_from_abs_origin(
        bbox: Sequence[float], image_ele: Dict[str, Any], *, tgt_format: str
    ) -> List[float]:
        x1, y1, x2, y2 = bbox
        width, height = image_ele["width"], image_ele["height"]
        if tgt_format == "abs_origin":
            return [int(x1), int(y1), int(x2), int(y2)]
        if tgt_format == "abs_resized":
            return [
                int(x1 / width * image_ele["resized_width"]),
                int(y1 / height * image_ele["resized_height"]),
                int(x2 / width * image_ele["resized_width"]),
                int(y2 / height * image_ele["resized_height"]),
            ]
        if tgt_format == "qwen-vl":
            return [
                int(x1 / width * 999),
                int(y1 / height * 999),
                int(x2 / width * 999),
                int(y2 / height * 999),
            ]
        if tgt_format == "rel":
            return [
                float(x1 / width),
                float(y1 / height),
                float(x2 / width),
                float(y2 / height),
            ]
        if tgt_format == "molmo":
            return [
                round(x1 / width * 100, 1),
                round(y1 / height * 100, 1),
                round(x2 / width * 100, 1),
                round(y2 / height * 100, 1),
            ]
        raise ValueError(f"Unknown tgt_format: {tgt_format}")

    @staticmethod
    def _convert_bbox_to_abs_origin(
        bbox: Sequence[float], image_ele: Dict[str, Any], *, src_format: str
    ) -> List[int]:
        x1, y1, x2, y2 = bbox
        width, height = image_ele["width"], image_ele["height"]
        if src_format == "abs_origin":
            return [int(x1), int(y1), int(x2), int(y2)]
        if src_format == "abs_resized":
            return [
                int(x1 / image_ele["resized_width"] * width),
                int(y1 / image_ele["resized_height"] * height),
                int(x2 / image_ele["resized_width"] * width),
                int(y2 / image_ele["resized_height"] * height),
            ]
        if src_format == "qwen-vl":
            return [
                int(x1 / 999 * width),
                int(y1 / 999 * height),
                int(x2 / 999 * width),
                int(y2 / 999 * height),
            ]
        if src_format == "rel":
            return [
                int(x1 * width),
                int(y1 * height),
                int(x2 * width),
                int(y2 * height),
            ]
        if src_format == "molmo":
            return [
                int(x1 / 100 * width),
                int(y1 / 100 * height),
                int(x2 / 100 * width),
                int(y2 / 100 * height),
            ]
        raise ValueError(f"Unknown src_format: {src_format}")

    @classmethod
    def convert_bbox_format(
        cls,
        bbox: Sequence[float],
        image_ele: Dict[str, Any],
        *,
        src_format: str,
        tgt_format: str,
    ) -> List[float]:
        bbox_abs_origin = cls._convert_bbox_to_abs_origin(
            bbox, image_ele, src_format=src_format
        )
        return cls._convert_bbox_from_abs_origin(
            bbox_abs_origin, image_ele, tgt_format=tgt_format
        )

    @staticmethod
    def _convert_point_from_abs_origin(
        point: Sequence[float], image_ele: Dict[str, Any], *, tgt_format: str
    ) -> List[float]:
        x, y = point
        width, height = image_ele["width"], image_ele["height"]
        if tgt_format == "abs_origin":
            return [int(x), int(y)]
        if tgt_format == "abs_resized":
            return [
                int(x / width * image_ele["resized_width"]),
                int(y / height * image_ele["resized_height"]),
            ]
        if tgt_format == "qwen-vl":
            return [int(x / width * 999), int(y / height * 999)]
        if tgt_format == "rel":
            return [float(x / width), float(y / height)]
        if tgt_format == "molmo":
            return [
                round(x / width * 100, 1),
                round(y / height * 100, 1),
            ]
        raise ValueError(f"Unknown tgt_format: {tgt_format}")

    @staticmethod
    def _convert_point_to_abs_origin(
        point: Sequence[float], image_ele: Dict[str, Any], *, src_format: str
    ) -> List[int]:
        x, y = point
        width, height = image_ele["width"], image_ele["height"]
        if src_format == "abs_origin":
            return [int(x), int(y)]
        if src_format == "abs_resized":
            return [
                int(x / image_ele["resized_width"] * width),
                int(y / image_ele["resized_height"] * height),
            ]
        if src_format == "qwen-vl":
            return [int(x / 999 * width), int(y / 999 * height)]
        if src_format == "rel":
            return [int(x * width), int(y * height)]
        if src_format == "molmo":
            return [int(x / 100 * width), int(y / 100 * height)]
        raise ValueError(f"Unknown src_format: {src_format}")

    @classmethod
    def convert_point_format(
        cls,
        point: Sequence[float],
        image_ele: Dict[str, Any],
        *,
        src_format: str,
        tgt_format: str,
    ) -> List[float]:
        point_abs_origin = cls._convert_point_to_abs_origin(
            point, image_ele, src_format=src_format
        )
        return cls._convert_point_from_abs_origin(
            point_abs_origin, image_ele, tgt_format=tgt_format
        )


# ---------------------------------------------------------------------- #
# Module-level convenience wrappers (retain legacy function names)
# ---------------------------------------------------------------------- #

_DEFAULT_PROCESSOR = ImageProcessor()

encode_numpy_image_to_base64 = ImageProcessor.encode_numpy_image_to_base64
encode_image_bytes = ImageProcessor.encode_image_bytes
downscale_image_bytes = ImageProcessor.downscale_image_bytes
encode_image = _DEFAULT_PROCESSOR.encode_image
format_image = _DEFAULT_PROCESSOR.format_image
format_text_message = _DEFAULT_PROCESSOR.format_text_message
create_system_message = _DEFAULT_PROCESSOR.create_system_message
create_user_message = _DEFAULT_PROCESSOR.create_user_message
create_assistant_message = _DEFAULT_PROCESSOR.create_assistant_message
dhash = ImageProcessor.dhash
round_by_factor = ImageProcessor.round_by_factor
ceil_by_factor = ImageProcessor.ceil_by_factor
floor_by_factor = ImageProcessor.floor_by_factor
smart_resize = ImageProcessor.smart_resize
update_image_size_ = ImageProcessor.update_image_size
convert_bbox_format = ImageProcessor.convert_bbox_format
convert_point_format = ImageProcessor.convert_point_format

__all__ = [
    "ImageProcessor",
    "encode_numpy_image_to_base64",
    "encode_image_bytes",
    "downscale_image_bytes",
    "encode_image",
    "format_image",
    "format_text_message",
    "create_system_message",
    "create_user_message",
    "create_assistant_message",
    "dhash",
    "round_by_factor",
    "ceil_by_factor",
    "floor_by_factor",
    "smart_resize",
    "update_image_size_",
    "convert_bbox_format",
    "convert_point_format",
]
