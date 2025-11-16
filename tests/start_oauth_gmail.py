"""
Start Gmail OAuth and print the authorization URL.

Usage:
  export SERVER_URL=http://localhost:8000
  export USER_ID=dev-local
  python -m tests.start_oauth_gmail

Open the printed URL in your browser to complete OAuth.
"""

import os
import sys
import requests


def main() -> int:
    base = os.getenv("SERVER_URL", "http://localhost:8000")
    user_id = os.getenv("USER_ID", "dev-local")
    url = f"{base.rstrip('/')}/api/mcp/auth/gmail/start"
    r = requests.get(url, headers={"X-User-Id": user_id}, timeout=30)
    if r.status_code != 200:
        print(f"HTTP {r.status_code}")
        try:
            print(r.text)
        except Exception:
            pass
        r.raise_for_status()
    data = r.json()
    print(data.get("authorization_url", ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
