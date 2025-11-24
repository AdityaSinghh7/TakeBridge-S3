#!/usr/bin/env python3
"""Delete the broken Gmail connected account."""

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

    connected_account_id = "ca_thWm04tNUKhT"  # The broken account

    print(f"=== Deleting Connected Account ===")
    print(f"Account ID: {connected_account_id}\n")

    confirm = input("Are you sure you want to DELETE this account? (yes/no): ")
    if confirm.lower() != "yes":
        print("Aborted.")
        sys.exit(0)

    url = f"{COMPOSIO_API_V3}/connected_accounts/{connected_account_id}"
    headers = {
        "x-api-key": COMPOSIO_KEY,
        "accept": "application/json"
    }

    try:
        response = requests.delete(url, headers=headers, timeout=15)
        response.raise_for_status()

        print("✓ Connected account deleted successfully\n")
        print("Now you can create a fresh connection:")
        print("  python3 scripts/fix_gmail_auth.py")

    except requests.HTTPError as e:
        if e.response.status_code == 404:
            print("⚠ Account not found (may already be deleted)")
        else:
            print(f"❌ HTTP Error: {e}")
            print(f"Response: {e.response.text[:500]}")
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
