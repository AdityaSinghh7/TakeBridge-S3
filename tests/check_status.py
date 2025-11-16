"""
Check MCP OAuth status for a development user.

Usage:
  export SERVER_URL=http://localhost:8000
  export USER_ID=dev-local
  python -m tests.check_status
"""

import os
import json
import requests


def main() -> int:
    base = os.getenv("SERVER_URL", "http://localhost:8000")
    user_id = os.getenv("USER_ID", "dev-local")
    url = f"{base.rstrip('/')}/api/mcp/auth/status"
    r = requests.get(url, headers={"X-User-Id": user_id}, timeout=30)
    r.raise_for_status()
    print(json.dumps(r.json(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
