"""
Debug MCP OAuth/Composio configuration and basic connectivity.

Endpoints queried (GET):
  - /api/mcp/auth/_debug/config
  - /api/mcp/auth/_debug/ping
  - /api/mcp/auth/_debug/auth-configs?provider={provider}
  - /api/mcp/auth/_debug/redirect/{provider}
  - /api/mcp/auth/status

Environment:
  SERVER_URL  (default: http://localhost:8000)
  USER_ID     (default: singleton)
  PROVIDER    (default: gmail)

Usage:
  export SERVER_URL=http://localhost:8000
  python -m tests.debug_oauth --provider gmail
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, Tuple

import requests


def _get(url: str, headers: Dict[str, str] | None = None, params: Dict[str, Any] | None = None) -> Tuple[int | str, Any]:
    try:
        r = requests.get(url, headers=headers or {}, params=params or {}, timeout=20)
        status = r.status_code
        try:
            body = r.json()
        except Exception:
            body = r.text
        return status, body
    except Exception as e:
        return "error", str(e)


def main() -> int:
    parser = argparse.ArgumentParser(description="Debug MCP OAuth/Composio endpoints")
    parser.add_argument("--provider", default=os.getenv("PROVIDER", "gmail"), help="Provider slug, e.g. gmail, slack")
    parser.add_argument("--base", default=os.getenv("SERVER_URL", "http://localhost:8000"), help="Server base URL")
    parser.add_argument("--user-id", default=os.getenv("USER_ID", "singleton"), help="User id header value")
    args = parser.parse_args()

    base = args.base.rstrip("/")
    provider = args.provider
    user_id = args.user_id

    headers = {"X-User-Id": user_id}

    checks = [
        ("config", f"{base}/api/mcp/auth/_debug/config", None),
        ("ping", f"{base}/api/mcp/auth/_debug/ping", None),
        ("auth_configs", f"{base}/api/mcp/auth/_debug/auth-configs", {"provider": provider}),
        ("redirect_example", f"{base}/api/mcp/auth/_debug/redirect/{provider}", None),
        ("status", f"{base}/api/mcp/auth/status", None),
    ]

    overall_ok = True
    out: Dict[str, Any] = {}

    for name, url, params in checks:
        status, body = _get(url, headers=headers, params=params)
        if isinstance(status, int):
            ok = 200 <= status < 300
        else:
            ok = False
        overall_ok = overall_ok and ok
        out[name] = {"ok": ok, "status": status, "data": body}

    print(json.dumps(out, indent=2))
    return 0 if overall_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

