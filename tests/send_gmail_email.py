"""
Send a test email through the TEST-ONLY MCP tools endpoint.

Environment:
  SERVER_URL=http://localhost:8000
  USER_ID=dev-local

Usage:
  python -m tests.send_gmail_email

Edit the payload below to change recipients and content.
"""

import os
import json
import requests


def main() -> int:
    base = os.getenv("SERVER_URL", "http://localhost:8000")
    user_id = os.getenv("USER_ID", "dev-local")
    url = f"{base.rstrip('/')}/api/mcp/tools/gmail/send_email"

    payload = {
        "to": "bhuvan035@gmail.com",
        "subject": "Hello from TakeBridge",
        "body": "This is a test.",
        "cc": "adityadevsinghs@gmail.com",
        "bcc": "lokhandesoham2703@gmail.com",
        "thread_id": "",
    }

    r = requests.post(url, headers={"X-User-Id": user_id}, json=payload, timeout=60)
    print(r.status_code)
    try:
        print(json.dumps(r.json(), indent=2))
    except Exception:
        print(r.text)
    r.raise_for_status()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
