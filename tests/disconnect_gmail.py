"""
Disconnect the Gmail provider for a development user.

Usage:
  export SERVER_URL=http://localhost:8000
  export USER_ID=dev-local
  python -m tests.disconnect_gmail
"""

import os
import json
import requests


def main() -> int:
    base = os.getenv("SERVER_URL", "http://localhost:8000")
    user_id = os.getenv("USER_ID", "dev-local")
    url = f"{base.rstrip('/')}/api/mcp/auth/gmail"
    r = requests.delete(url, headers={"X-User-Id": user_id}, timeout=30)
    print(r.status_code)
    try:
        print(json.dumps(r.json(), indent=2))
    except Exception:
        print(r.text)
    r.raise_for_status()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
