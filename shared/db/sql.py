from __future__ import annotations

from typing import Any, Mapping

from sqlalchemy import text
from sqlalchemy.engine import Result
from sqlalchemy.orm import Session


_FORBIDDEN_SQL_TOKENS = (
    "{",
    "}",
    "%(",
)


def execute_text(db: Session, sql: str, params: Mapping[str, Any] | None = None) -> Result:
    """
    Execute a raw SQL string safely using SQLAlchemy bound parameters.

    This helper is meant to centralize raw SQL execution and make it harder to
    accidentally introduce string interpolation into SQL.
    """
    if params is None:
        params = {}
    if not isinstance(sql, str) or not sql.strip():
        raise ValueError("sql must be a non-empty string")
    if any(token in sql for token in _FORBIDDEN_SQL_TOKENS):
        raise ValueError("sql contains a forbidden formatting token; use bind params instead")
    return db.execute(text(sql), dict(params))


__all__ = ["execute_text"]
