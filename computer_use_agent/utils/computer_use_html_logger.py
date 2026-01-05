from __future__ import annotations

import base64
import html
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

_DEFAULT_LOG_DIR = "logs/computer_use_logs"
_FOOTER = "\n</main>\n</body>\n</html>\n"
_FOOTER_BYTES = _FOOTER.encode("ascii")


def _sanitize_run_id(value: Optional[str]) -> str:
    if not value:
        return "unknown"
    cleaned = "".join(ch for ch in value if ch.isalnum() or ch in {"-", "_"})
    return cleaned or "unknown"


def _detect_image_mime(image_bytes: bytes) -> str:
    if image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if image_bytes.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if image_bytes.startswith(b"GIF87a") or image_bytes.startswith(b"GIF89a"):
        return "image/gif"
    if image_bytes.startswith(b"BM"):
        return "image/bmp"
    if len(image_bytes) >= 12 and image_bytes[:4] == b"RIFF" and image_bytes[8:12] == b"WEBP":
        return "image/webp"
    return "application/octet-stream"


def _data_uri(image_bytes: bytes) -> str:
    mime = _detect_image_mime(image_bytes)
    encoded = base64.b64encode(image_bytes).decode("ascii")
    return f"data:{mime};base64,{encoded}"


class ComputerUseHtmlLogger:
    def __init__(self, run_id: Optional[str]) -> None:
        self.run_id = _sanitize_run_id(run_id)
        log_dir = Path(os.getenv("COMPUTER_USE_LOG_DIR", _DEFAULT_LOG_DIR)).expanduser()
        self.path = log_dir / f"computer-use-{self.run_id}.html"
        self._lock = threading.Lock()
        self._init_file()

    def _init_file(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        except Exception:
            return

        header = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Computer Use Log</title>
  <style>
    :root { color-scheme: light; }
    body { margin: 0; font-family: ui-sans-serif, system-ui, -apple-system, "Segoe UI", Arial, sans-serif; color: #111; background: #f6f6f6; }
    main { max-width: 1200px; margin: 0 auto; padding: 16px; }
    .run-header { background: #fff; border: 1px solid #e0e0e0; padding: 12px 16px; border-radius: 8px; }
    .step { margin-top: 16px; background: #fff; border: 1px solid #e0e0e0; padding: 12px 16px; border-radius: 8px; }
    .step h2 { margin: 0 0 8px 0; font-size: 18px; }
    .meta { display: grid; grid-template-columns: max-content 1fr; gap: 6px 12px; font-size: 13px; color: #333; }
    .meta .label { color: #666; }
    .block { margin-top: 10px; }
    .block-title { font-size: 13px; color: #666; margin-bottom: 4px; }
    pre { margin: 0; padding: 8px; background: #f2f2f2; border-radius: 6px; white-space: pre-wrap; word-break: break-word; }
    .images { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 12px; margin-top: 12px; }
    figure { margin: 0; }
    figcaption { font-size: 12px; color: #555; margin-bottom: 4px; }
    img { width: 100%; height: auto; border: 1px solid #ddd; border-radius: 6px; background: #fafafa; }
  </style>
</head>
<body>
<main>
"""
        if self.path.exists():
            self._truncate_footer()
            try:
                if self.path.stat().st_size == 0:
                    self._append(header)
            except Exception:
                pass
            return

        self._append(header)

    def _truncate_footer(self) -> None:
        try:
            with open(self.path, "rb+") as handle:
                handle.seek(0, 2)
                size = handle.tell()
                if size == 0:
                    return
                tail_size = min(size, 512)
                handle.seek(size - tail_size)
                tail = handle.read(tail_size)
                idx = tail.rfind(_FOOTER_BYTES)
                if idx == -1:
                    return
                new_size = size - (len(tail) - idx)
                handle.truncate(new_size)
        except Exception:
            pass

    def _append(self, content: str) -> None:
        try:
            with self._lock:
                with open(self.path, "a", encoding="utf-8") as handle:
                    handle.write(content)
        except Exception:
            pass

    def log_run_start(self, task: str, platform: Optional[str]) -> None:
        ts = datetime.now(timezone.utc).isoformat()
        task_text = html.escape(task or "")
        platform_text = html.escape(platform or "")
        run_id_text = html.escape(self.run_id)
        content = (
            '<section class="run-header">'
            f"<div><strong>Run</strong> {run_id_text}</div>"
            f"<div><strong>Started</strong> {ts}</div>"
            f"<div><strong>Platform</strong> {platform_text}</div>"
            f"<div><strong>Task</strong> {task_text}</div>"
            "</section>\n"
        )
        self._append(content)

    def log_step(
        self,
        *,
        step_index: int,
        action: str,
        exec_code: str,
        execution_mode: str,
        status: str,
        completion_reason: Optional[str],
        plan: Optional[str],
        reflection: Optional[str],
        handback_request: Optional[str],
        behavior_fact: Optional[str],
        behavior_thoughts: Optional[str],
        before_img: Optional[bytes],
        after_img: Optional[bytes],
        delayed_after_img: Optional[bytes],
        marked_before_img: Optional[bytes],
        marked_after_img: Optional[bytes],
        zoomed_after_img: Optional[bytes],
    ) -> None:
        ts = datetime.now(timezone.utc).isoformat()
        lines = [f'<section class="step"><h2>Step {step_index}</h2>']
        meta = [
            ("timestamp", ts),
            ("execution_mode", execution_mode),
            ("status", status),
            ("completion_reason", completion_reason or ""),
        ]
        lines.append('<div class="meta">')
        for key, value in meta:
            if value:
                lines.append(
                    f'<div class="label">{html.escape(key)}</div>'
                    f"<div>{html.escape(str(value))}</div>"
                )
        lines.append("</div>")

        if handback_request:
            lines.append('<div class="block">')
            lines.append('<div class="block-title">handback_request</div>')
            lines.append(f"<pre>{html.escape(handback_request)}</pre>")
            lines.append("</div>")

        if action:
            lines.append('<div class="block">')
            lines.append('<div class="block-title">action</div>')
            lines.append(f"<pre>{html.escape(action)}</pre>")
            lines.append("</div>")

        if exec_code and exec_code != action:
            lines.append('<div class="block">')
            lines.append('<div class="block-title">exec_code</div>')
            lines.append(f"<pre>{html.escape(exec_code)}</pre>")
            lines.append("</div>")

        if plan:
            lines.append('<div class="block">')
            lines.append('<div class="block-title">plan</div>')
            lines.append(f"<pre>{html.escape(plan)}</pre>")
            lines.append("</div>")

        if reflection:
            lines.append('<div class="block">')
            lines.append('<div class="block-title">reflection</div>')
            lines.append(f"<pre>{html.escape(reflection)}</pre>")
            lines.append("</div>")

        if behavior_fact:
            lines.append('<div class="block">')
            lines.append('<div class="block-title">behavior_fact</div>')
            lines.append(f"<pre>{html.escape(behavior_fact)}</pre>")
            lines.append("</div>")

        if behavior_thoughts:
            lines.append('<div class="block">')
            lines.append('<div class="block-title">behavior_thoughts</div>')
            lines.append(f"<pre>{html.escape(behavior_thoughts)}</pre>")
            lines.append("</div>")

        image_blocks = []
        image_blocks.extend(
            self._render_image("before", before_img),
        )
        image_blocks.extend(
            self._render_image("after", after_img),
        )
        image_blocks.extend(
            self._render_image("after_delayed", delayed_after_img),
        )
        image_blocks.extend(
            self._render_image("before_marked", marked_before_img),
        )
        image_blocks.extend(
            self._render_image("after_marked", marked_after_img),
        )
        image_blocks.extend(
            self._render_image("after_zoomed", zoomed_after_img),
        )
        if image_blocks:
            lines.append('<div class="images">')
            lines.extend(image_blocks)
            lines.append("</div>")

        lines.append("</section>\n")
        self._append("\n".join(lines))

    def _render_image(self, label: str, image_bytes: Optional[bytes]) -> list[str]:
        if not image_bytes:
            return []
        uri = _data_uri(image_bytes)
        safe_label = html.escape(label)
        return [
            "<figure>",
            f"<figcaption>{safe_label}</figcaption>",
            f'<img src="{uri}" alt="{safe_label}" loading="lazy">',
            "</figure>",
        ]

    def log_run_end(self, status: str, completion_reason: str) -> None:
        ts = datetime.now(timezone.utc).isoformat()
        content = (
            '<section class="run-header">'
            f"<div><strong>Ended</strong> {ts}</div>"
            f"<div><strong>Status</strong> {html.escape(status)}</div>"
            f"<div><strong>Completion</strong> {html.escape(completion_reason)}</div>"
            "</section>\n"
        )
        self._append(content)
        self._append(_FOOTER)
