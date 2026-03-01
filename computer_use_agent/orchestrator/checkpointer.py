from __future__ import annotations

import atexit
import logging
import os
import threading
from typing import Any, Optional
from urllib.parse import urlparse, urlunparse

from shared.db.engine import DB_URL

logger = logging.getLogger(__name__)

_CHECKPOINTER_LOCK = threading.Lock()
_CHECKPOINTER: Optional[Any] = None
_CHECKPOINTER_CM: Optional[Any] = None
_CHECKPOINTER_SETUP_DONE = False


def _is_test_mode() -> bool:
    if os.getenv("PYTEST_CURRENT_TEST"):
        return True
    return os.getenv("COMPUTER_USE_TEST_MODE", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _normalize_postgres_dsn(db_url: str) -> str:
    parsed = urlparse(db_url)
    scheme = parsed.scheme
    if "+" in scheme:
        scheme = scheme.split("+", 1)[0]
    if scheme == "postgresql":
        scheme = "postgresql"
    elif scheme == "postgres":
        scheme = "postgres"
    else:
        raise ValueError(f"Unsupported DB scheme for LangGraph checkpointer: {parsed.scheme}")
    return urlunparse(
        (
            scheme,
            parsed.netloc,
            parsed.path,
            parsed.params,
            parsed.query,
            parsed.fragment,
        )
    )


def _is_postgres_url(db_url: str) -> bool:
    scheme = urlparse(db_url).scheme.split("+", 1)[0]
    return scheme in {"postgresql", "postgres"}


def _close_checkpointer() -> None:
    global _CHECKPOINTER, _CHECKPOINTER_CM
    if _CHECKPOINTER_CM is not None:
        try:
            _CHECKPOINTER_CM.__exit__(None, None, None)
        except Exception:
            logger.debug("Failed to close LangGraph Postgres checkpointer cleanly", exc_info=True)
    _CHECKPOINTER = None
    _CHECKPOINTER_CM = None


def get_graph_checkpointer() -> Any:
    global _CHECKPOINTER, _CHECKPOINTER_CM, _CHECKPOINTER_SETUP_DONE
    if _CHECKPOINTER is not None:
        return _CHECKPOINTER

    with _CHECKPOINTER_LOCK:
        if _CHECKPOINTER is not None:
            return _CHECKPOINTER

        is_test_mode = _is_test_mode()
        if not _is_postgres_url(DB_URL):
            if not is_test_mode:
                raise RuntimeError(
                    "LangGraph checkpointer requires a Postgres DB_URL outside test mode."
                )
            from langgraph.checkpoint.memory import InMemorySaver

            logger.warning(
                "Using in-memory LangGraph checkpointer because DB_URL is not Postgres in test mode."
            )
            _CHECKPOINTER = InMemorySaver()
            _CHECKPOINTER_SETUP_DONE = True
            return _CHECKPOINTER

        from langgraph.checkpoint.postgres import PostgresSaver

        dsn = _normalize_postgres_dsn(DB_URL)
        _CHECKPOINTER_CM = PostgresSaver.from_conn_string(dsn)
        _CHECKPOINTER = _CHECKPOINTER_CM.__enter__()
        if not _CHECKPOINTER_SETUP_DONE:
            _CHECKPOINTER.setup()
            _CHECKPOINTER_SETUP_DONE = True
        atexit.register(_close_checkpointer)
        return _CHECKPOINTER

