"""
Quick DB connectivity + optional table counts.
"""
from dotenv import load_dotenv
load_dotenv()

import os
from sqlalchemy import text
from framework.db.engine import engine, session_scope
from framework.db.models import User, ConnectedAccount, MCPConnection

def main() -> int:
    url = os.getenv("DB_URL", "sqlite:///./takebridge.db")
    print(f"DB_URL={url}")

    # Basic connectivity
    with engine.connect() as conn:
        one = conn.execute(text("SELECT 1")).scalar_one()
        print(f"select 1 -> {one}")

    # Optional counts (after migrations)
    try:
        with session_scope() as db:
            users = db.query(User).count()
            cas = db.query(ConnectedAccount).count()
            mcp = db.query(MCPConnection).count()
        print({"users": users, "connected_accounts": cas, "mcp_connections": mcp})
    except Exception as e:
        print(f"Counts failed (likely before migrations): {e}")

    return 0

if __name__ == "__main__":
    raise SystemExit(main())
