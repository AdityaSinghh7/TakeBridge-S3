from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional


class LatencyLogger:
    """Thread-safe JSONL latency logger used across orchestrator components."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        run_id = os.getenv("RUN_LOG_ID") or datetime.now().strftime("%Y%m%d@%H%M%S")
        self._logs_dir = Path("logs")
        try:
            self._logs_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            self._logs_dir = Path(".")
        self._log_path = self._logs_dir / f"latency-{run_id}.jsonl"

    def log_event(
        self,
        component: str,
        event: str,
        duration_ms: float,
        extra: Optional[Dict[str, Any]] = None,
    ) -> None:
        record = {
            "ts": datetime.utcnow().isoformat() + "Z",
            "pid": os.getpid(),
            "component": component,
            "event": event,
            "duration_ms": round(float(duration_ms), 3),
        }
        if extra:
            try:
                record["extra"] = json.loads(json.dumps(extra, ensure_ascii=False))
            except Exception:
                record["extra"] = str(extra)
        try:
            with self._lock:
                with open(self._log_path, "a", encoding="utf-8") as fp:
                    fp.write(json.dumps(record, ensure_ascii=False) + "\n")
                print(f"[LATENCY] {json.dumps(record, ensure_ascii=False)}")
        except Exception:
            pass

    def measure(
        self,
        component: str,
        event: str,
        extra: Optional[Dict[str, Any]] = None,
    ):

        class _Timer:
            def __enter__(inner_self):
                inner_self._start = time.perf_counter()
                return inner_self

            def __exit__(inner_self, exc_type, exc_val, exc_tb):
                duration_ms = (time.perf_counter() - inner_self._start) * 1000.0
                self.log_event(component, event, duration_ms, extra)

        return _Timer()


LATENCY_LOGGER = LatencyLogger()

