#!/usr/bin/env python3
"""Complete Gmail OAuth flow by finding the newly created connected account."""

import json
import os
import sys
from pathlib import Path

import requests

# Add project root to path
repo_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(repo_root))
os.environ['PYTHONPATH'] = str(repo_root)

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

    print("=== Finding newly created Gmail connected account ===\n")

    # List all connected accounts for dev-local
    url = f"{COMPOSIO_API_V3}/connected_accounts"
    headers = {
        "x-api-key": COMPOSIO_KEY,
        "accept": "application/json"
    }
    params = {
        "user_id": "dev-local"
    }

    try:
        response = requests.get(url, headers=headers, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()

        # Look for Gmail accounts
        items = data.get("items") or data.get("data") or []
        gmail_accounts = []

        for account in items:
            toolkit = account.get("toolkit") or {}
            if toolkit.get("slug") == "gmail" and account.get("status") == "ACTIVE":
                gmail_accounts.append(account)

        if not gmail_accounts:
            print("❌ No active Gmail connected accounts found for dev-local")
            print("\nThis might mean:")
            print("  1. The OAuth flow didn't complete successfully")
            print("  2. The account status is still initializing")
            print("  3. The account was created under a different user_id")
            sys.exit(1)

        # Sort by created_at (most recent first)
        gmail_accounts.sort(key=lambda x: x.get("created_at", ""), reverse=True)

        print(f"Found {len(gmail_accounts)} Gmail account(s):")
        for i, acc in enumerate(gmail_accounts, 1):
            print(f"\n{i}. ID: {acc.get('id')}")
            print(f"   Status: {acc.get('status')}")
            print(f"   Created: {acc.get('created_at')}")
            print(f"   Updated: {acc.get('updated_at')}")

        # Use the most recent one
        newest = gmail_accounts[0]
        ca_id = newest.get("id")

        print(f"\n=== Using most recent account: {ca_id} ===")

        # Import after setting up path
        from mcp_agent.core.context import AgentContext
        from mcp_agent.registry.oauth import OAuthManager

        context = AgentContext.create(user_id="dev-local", request_id="finalize")

        print("\nFinalizing connected account...")
        result = OAuthManager.finalize_connected_account(context, "gmail", ca_id)

        print("\n✓ Gmail reconnected successfully!")
        print(f"\nConnection details:")
        print(f"  Provider: {result.get('provider')}")
        print(f"  Account ID: {result.get('connected_account_id')}")
        print(f"  MCP URL: {result.get('mcp_url')}")

        print("\n=== Testing connection ===")
        from mcp_agent.registry.crud import get_mcp_client

        try:
            gmail_client = get_mcp_client(context, "gmail")
            print("✓ Gmail client created successfully")
            print("\nYou can now test with:")
            print("  python3 scripts/probe_tools.py")
        except Exception as e:
            print(f"⚠ Warning: {e}")

    except requests.HTTPError as e:
        print(f"❌ HTTP Error: {e}")
        print(f"Response: {e.response.text[:500]}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
