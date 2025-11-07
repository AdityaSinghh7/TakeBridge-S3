"""
Check MCP OAuth status for the singleton user.

Usage:
  export SERVER_URL=http://localhost:8000
  python -m tests.check_status
"""

import os
import json
import requests


def main() -> int:
    base = os.getenv("SERVER_URL", "http://localhost:8000")
    url = f"{base.rstrip('/')}/api/mcp/auth/status"
    r = requests.get(url, headers={"X-User-Id": "singleton"}, timeout=30)
    r.raise_for_status()
    print(json.dumps(r.json(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

