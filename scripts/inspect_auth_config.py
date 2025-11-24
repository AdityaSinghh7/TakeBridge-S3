#!/usr/bin/env python3
"""Inspect Composio auth config details via API."""

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

    auth_config_id = "ac__kYlScI5FgLX"  # From your connected account

    print(f"=== Fetching Auth Config Details ===")
    print(f"Auth Config ID: {auth_config_id}\n")

    url = f"{COMPOSIO_API_V3}/auth-configs/{auth_config_id}"
    headers = {
        "x-api-key": COMPOSIO_KEY,
        "accept": "application/json"
    }

    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        data = response.json()

        print("=== Auth Config Details ===")
        print(f"ID: {data.get('id')}")
        print(f"Name: {data.get('name') or data.get('label')}")
        print(f"Auth Scheme: {data.get('auth_scheme')}")
        print(f"Is Composio Managed: {data.get('is_composio_managed')}")
        print(f"Is Disabled: {data.get('is_disabled')}")

        print("\n=== OAuth Configuration ===")
        params = data.get('parameters') or data.get('params') or {}
        if 'client_id' in params:
            print(f"✓ client_id: {params['client_id'][:20]}...")
        else:
            print("✗ client_id: MISSING")

        if 'client_secret' in params:
            print(f"✓ client_secret: ***{params['client_secret'][-8:]}")
        else:
            print("✗ client_secret: MISSING")

        if 'token_uri' in params:
            print(f"✓ token_uri: {params['token_uri']}")
        else:
            print("✗ token_uri: MISSING")

        print("\n=== Full Response (for debugging) ===")
        print(json.dumps(data, indent=2, default=str))

    except requests.HTTPError as e:
        print(f"❌ HTTP Error: {e}")
        print(f"Response: {e.response.text[:500]}")
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    main()
