#!/usr/bin/env python3
"""Inspect Composio connected account details via API."""

import json
import os
import sys

import requests

# Get Composio config from environment
COMPOSIO_HOST = os.getenv(
    "COMPOSIO_API_BASE",
    os.getenv("COMPOSIO_BASE_URL", "https://backend.composio.dev")
).rstrip("/")
COMPOSIO_KEY = os.getenv("COMPOSIO_API_KEY", "")
COMPOSIO_API_V3 = f"{COMPOSIO_HOST}/api/v3"

def main():
    if not COMPOSIO_KEY:
        print("❌ COMPOSIO_API_KEY not set in environment")
        sys.exit(1)

    connected_account_id = "ca_thWm04tNUKhT"  # From your database

    print(f"=== Fetching Connected Account Details ===")
    print(f"Account ID: {connected_account_id}\n")

    url = f"{COMPOSIO_API_V3}/connected_accounts/{connected_account_id}"
    headers = {
        "x-api-key": COMPOSIO_KEY,
        "accept": "application/json"
    }

    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        data = response.json()

        print("=== Account Status ===")
        print(f"Status: {data.get('status')}")
        print(f"Provider: {data.get('provider')}")
        print(f"User ID: {data.get('user_id')}")
        print(f"Provider UID: {data.get('provider_uid')}")

        print("\n=== Auth Config ===")
        auth_config = data.get('auth_config') or data.get('authConfig') or {}
        print(f"ID: {auth_config.get('id')}")
        print(f"Name: {auth_config.get('name')}")

        print("\n=== Credentials (High-Level) ===")
        # Note: Composio doesn't expose actual credentials via API for security
        # But we can check if the account is active and has auth_refresh_required flag
        print(f"Auth Refresh Required: {data.get('auth_refresh_required', False)}")

        print("\n=== MCP Server Info ===")
        mcp_info = data.get('mcp') or data.get('mcpServer') or {}
        print(f"MCP URL: {mcp_info.get('http_url') or mcp_info.get('url')}")

        print("\n=== Full Response (for debugging) ===")
        print(json.dumps(data, indent=2, default=str))

    except requests.HTTPError as e:
        print(f"❌ HTTP Error: {e}")
        print(f"Response: {e.response.text[:500]}")
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    main()
