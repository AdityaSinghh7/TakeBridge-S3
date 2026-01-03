from __future__ import annotations

import atexit
import json
import logging
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Tuple

try:
    import fcntl  # type: ignore
except Exception:  # pragma: no cover
    fcntl = None

from shared.run_context import RUN_LOG_ID


class TokenCostTracker:
    RATES_PER_TOKEN = {
        "o4-mini": {
            "input_new": 1.10 / 1_000_000.0,
            "input_cached": 0.275 / 1_000_000.0,
            "output": 4.40 / 1_000_000.0,
        },
        "deepseek-reasoner": {
            "input_new": 0.28 / 1_000_000.0,
            "input_cached": 0.028 / 1_000_000.0,
            "output": 0.42 / 1_000_000.0,
        },
        "gpt-5-nano-2025-08-07": {
            "input_new": 0.05 / 1_000_000.0,
            "input_cached": 0.005 / 1_000_000.0,
            "output": 0.4 / 1_000_000.0,
        },
    }

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.total_input_cached = 0
        self.total_input_new = 0
        self.total_output = 0
        self.total_cost_usd = 0.0
        self.summary_written = False
        run_id = os.getenv("RUN_LOG_ID") or datetime.now().strftime("%Y%m%d@%H%M%S")
        self.logs_dir = Path("logs")
        try:
            self.logs_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        self.log_path = self.logs_dir / f"token-costs-{run_id}.jsonl"

    def _append_jsonl(self, obj: Dict[str, Any]) -> None:
        line = json.dumps(obj, ensure_ascii=False)
        try:
            with open(self.log_path, "a", encoding="utf-8") as fp:
                if fcntl is not None:
                    try:
                        fcntl.flock(fp.fileno(), fcntl.LOCK_EX)
                    except Exception:
                        pass
                fp.write(line + "\n")
                try:
                    if fcntl is not None:
                        fcntl.flock(fp.fileno(), fcntl.LOCK_UN)
                except Exception:
                    pass
        except Exception:
            pass

    @staticmethod
    def _get_attr(obj: Any, name: str, default: Any = 0) -> Any:
        if obj is None:
            return default
        if isinstance(obj, dict):
            return obj.get(name, default)
        return getattr(obj, name, default)

    def _extract_usage(self, response: Any) -> Tuple[int, int, int]:
        usage = getattr(response, "usage", None)
        if usage is None and hasattr(response, "model_dump"):
            try:
                usage = response.model_dump().get("usage", None)
            except Exception:
                usage = None

        input_total = 0
        output = 0
        cached = 0

        if usage is not None:
            input_total = (
                self._get_attr(usage, "input_tokens", 0)
                or self._get_attr(usage, "prompt_tokens", 0)
            )
            output = (
                self._get_attr(usage, "output_tokens", 0)
                or self._get_attr(usage, "completion_tokens", 0)
            )
            cached = (
                self._get_attr(usage, "input_cached_tokens", 0)
                or self._get_attr(usage, "input_tokens_cached", 0)
            )
            if not cached:
                details = self._get_attr(usage, "prompt_tokens_details", None)
                cached = self._get_attr(details, "cached_tokens", 0)

        input_new = max(int(input_total) - int(cached), 0)
        return int(cached or 0), int(input_new or 0), int(output or 0)

    def record_response(
        self,
        model: str,
        source: str,
        response: Any,
        logger: logging.Logger | None = None,
    ) -> None:
        try:
            cached, new_input, output = self._extract_usage(response)
        except Exception:
            cached = new_input = output = 0

        rates = self.RATES_PER_TOKEN.get(model)
        cost_cached = (cached * rates["input_cached"]) if rates else 0.0
        cost_new = (new_input * rates["input_new"]) if rates else 0.0
        cost_output = (output * rates["output"]) if rates else 0.0
        total = cost_cached + cost_new + cost_output

        with self.lock:
            self.total_input_cached += cached
            self.total_input_new += new_input
            self.total_output += output
            self.total_cost_usd += total

            entry = {
                "type": "call",
                "ts": datetime.utcnow().isoformat() + "Z",
                "pid": os.getpid(),
                "model": model,
                "source": source,
                "tokens": {
                    "input_cached": cached,
                    "input_new": new_input,
                    "output": output,
                },
                "cost_usd": {
                    "input_cached": round(cost_cached, 8),
                    "input_new": round(cost_new, 8),
                    "output": round(cost_output, 8),
                    "total": round(total, 8),
                },
                "totals_after": {
                    "input_cached": self.total_input_cached,
                    "input_new": self.total_input_new,
                    "output": self.total_output,
                    "cost_usd": round(self.total_cost_usd, 8),
                },
            }
            self._append_jsonl(entry)

        if os.getenv("TOKEN_COST_DB_ENABLED", "1").lower() in {"1", "true", "yes"}:
            run_id = RUN_LOG_ID.get()
            if run_id:
                try:
                    from shared.db.user_metadata import record_token_usage

                    record_token_usage(
                        run_id=run_id,
                        delta_tokens={
                            "input_cached": cached,
                            "input_new": new_input,
                            "output": output,
                        },
                        delta_cost_usd=total,
                        model=model,
                        source=source,
                    )
                except Exception:
                    pass

        line = (
            f"[TOKENS] model={model} src={source} cached={cached} new={new_input} "
            f"out={output} cost=${total:.6f} (run_total=${self.total_cost_usd:.6f})"
        )
        print(line)
        if logger:
            try:
                logger.info(line)
            except Exception:
                pass

    def write_summary(self, logger: logging.Logger | None = None) -> None:
        with self.lock:
            if self.summary_written:
                return
            self.summary_written = True
            entry = {
                "type": "summary",
                "ts": datetime.utcnow().isoformat() + "Z",
                "pid": os.getpid(),
                "totals": {
                    "input_cached": self.total_input_cached,
                    "input_new": self.total_input_new,
                    "output": self.total_output,
                },
                "cost_usd_total": round(self.total_cost_usd, 8),
            }
            self._append_jsonl(entry)
        line = (
            f"[TOKENS][SUMMARY] cached={self.total_input_cached} "
            f"new={self.total_input_new} out={self.total_output} "
            f"cost_total=${self.total_cost_usd:.6f}"
        )
        print(line)
        if logger:
            try:
                logger.info(line)
            except Exception:
                pass


TOKEN_TRACKER = TokenCostTracker()
atexit.register(TOKEN_TRACKER.write_summary)
