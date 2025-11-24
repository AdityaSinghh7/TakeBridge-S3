#!/usr/bin/env python3
"""List available auth configs for Gmail."""

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

    print("=== Listing Auth Configs ===\n")

    url = f"{COMPOSIO_API_V3}/auth-configs"
    headers = {
        "x-api-key": COMPOSIO_KEY,
        "accept": "application/json"
    }

    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        data = response.json()

        items = data.get("items") or data.get("data") or []

        print(f"Found {len(items)} auth config(s):\n")

        gmail_configs = []
        for config in items:
            # Check if it's for Gmail (might be via integrationId or other field)
            config_id = config.get("id")
            name = config.get("name") or config.get("label") or "N/A"
            is_managed = config.get("is_composio_managed", False)
            is_disabled = config.get("is_disabled", False)
            auth_scheme = config.get("auth_scheme", "N/A")

            # Try to determine if it's for Gmail
            integration = config.get("integration") or config.get("integrationId") or {}
            if isinstance(integration, dict):
                app_name = integration.get("appName") or integration.get("app_name") or ""
            else:
                app_name = str(integration)

            print(f"ID: {config_id}")
            print(f"  Name: {name}")
            print(f"  Auth Scheme: {auth_scheme}")
            print(f"  Composio Managed: {is_managed}")
            print(f"  Disabled: {is_disabled}")
            if app_name:
                print(f"  App: {app_name}")
            print()

            if "gmail" in name.lower() or "gmail" in app_name.lower():
                gmail_configs.append(config)

        if gmail_configs:
            print(f"\n=== Gmail-specific configs ({len(gmail_configs)}) ===")
            for cfg in gmail_configs:
                print(f"  • {cfg.get('id')}: {cfg.get('name')} (managed={cfg.get('is_composio_managed')})")

        # Show current config
        current = os.getenv("COMPOSIO_GMAIL_AUTH_CONFIG_ID", "(not set)")
        print(f"\n=== Current .env setting ===")
        print(f"  COMPOSIO_GMAIL_AUTH_CONFIG_ID={current}")

    except requests.HTTPError as e:
        print(f"❌ HTTP Error: {e}")
        print(f"Response: {e.response.text[:500]}")
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
