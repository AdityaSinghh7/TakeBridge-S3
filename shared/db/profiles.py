from __future__ import annotations

from sqlalchemy.engine import Row
from sqlalchemy.orm import Session

from shared.db.sql import execute_text


def debit_credits(db: Session, *, user_id: str, cost: int) -> int | None:
    """
    Atomically decrement credits for a user if they have enough.

    Returns the remaining credits or None if insufficient credits / user missing.
    """
    row: Row | None = (
        execute_text(
            db,
            """
            UPDATE profiles
            SET credits = credits - :cost
            WHERE id = :user_id AND credits >= :cost
            RETURNING credits
            """,
            {"cost": cost, "user_id": user_id},
        ).fetchone()
    )
    if not row:
        return None
    return int(row[0])


__all__ = ["debit_credits"]
