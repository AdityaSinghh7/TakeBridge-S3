"""
Inspect DB-backed OAuth/MCP state per provider for the current user.

Usage:
  export DB_URL=...            # ensure this matches the server
  export USER_ID=singleton     # or your real user id
  python -m tests.inspect_auth
"""
from __future__ import annotations

from dotenv import load_dotenv
load_dotenv()

import os
from typing import Any, Dict

from framework.db.engine import session_scope
from framework.db.models import ConnectedAccount, MCPConnection


def inspect(user_id: str) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    with session_scope() as db:
        for prov in ("slack", "gmail"):
            row = (
                db.query(ConnectedAccount.id, ConnectedAccount.provider, ConnectedAccount.status, MCPConnection.mcp_url)
                .join(MCPConnection, MCPConnection.connected_account_id == ConnectedAccount.id, isouter=True)
                .filter(ConnectedAccount.user_id == user_id, ConnectedAccount.provider == prov)
                .order_by(MCPConnection.id.desc())
                .first()
            )
            if row:
                out[prov] = {
                    "connected_account_id": row[0],
                    "provider": row[1],
                    "status": row[2],
                    "mcp_url": row[3],
                }
            else:
                out[prov] = None
    return out


def main() -> int:
    user_id = os.getenv("USER_ID", "singleton")
    print({"user_id": user_id, "providers": inspect(user_id)})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

