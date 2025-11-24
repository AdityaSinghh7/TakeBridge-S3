#!/usr/bin/env python3
"""Test if Composio allows manual credential injection/updates."""

import json
import os
import sys
import requests

COMPOSIO_KEY = os.getenv("COMPOSIO_API_KEY")
COMPOSIO_API = "https://backend.composio.dev/api/v3"

def test_manual_credential_creation():
    """Test if we can create a connected account with manual credentials."""
    print("=== Test 1: Create Connected Account with Manual Credentials ===\n")

    response = requests.post(
        f"{COMPOSIO_API}/connected_accounts",
        headers={
            "x-api-key": COMPOSIO_KEY,
            "Content-Type": "application/json"
        },
        json={
            "user_id": "test-manual-creds",
            "integration": "gmail",
            # Try various credential injection patterns
            "credentials": {
                "access_token": "test_access_token_123",
                "refresh_token": "test_refresh_token_456",
                "token_type": "Bearer",
                "expires_at": 9999999999
            }
        }
    )

    print(f"Status: {response.status_code}")
    print(f"Response:\n{json.dumps(response.json(), indent=2)}\n")

    if response.status_code in (200, 201):
        print("✓ SUCCESS: Manual credential creation is supported!")
        return response.json().get("id")
    else:
        print("✗ FAILED: Manual credential creation not supported")
        return None


def test_credential_update(account_id):
    """Test if we can update existing credentials."""
    print(f"=== Test 2: Update Credentials for {account_id} ===\n")

    # Try different endpoint patterns
    endpoints = [
        f"{COMPOSIO_API}/connected_accounts/{account_id}/credentials",
        f"{COMPOSIO_API}/connected_accounts/{account_id}",
    ]

    for endpoint in endpoints:
        print(f"Trying: {endpoint}")
        response = requests.patch(
            endpoint,
            headers={
                "x-api-key": COMPOSIO_KEY,
                "Content-Type": "application/json"
            },
            json={
                "credentials": {
                    "access_token": "updated_access_token_789",
                    "refresh_token": "updated_refresh_token_012",
                    "expires_at": 9999999999
                }
            }
        )

        print(f"  Status: {response.status_code}")
        if response.status_code in (200, 204):
            print(f"  ✓ SUCCESS: Credential update supported via {endpoint}")
            return True

        print(f"  ✗ Failed: {response.text[:200]}\n")

    print("✗ OVERALL: Credential updates not supported\n")
    return False


def test_existing_account_update():
    """Test updating the existing broken Gmail account."""
    print("=== Test 3: Update Existing Gmail Account (ca_thWm04tNUKhT) ===\n")

    account_id = "ca_thWm04tNUKhT"

    # Get current credentials from Composio's stored data
    get_response = requests.get(
        f"{COMPOSIO_API}/connected_accounts/{account_id}",
        headers={"x-api-key": COMPOSIO_KEY}
    )

    if get_response.status_code == 200:
        data = get_response.json()
        current_creds = data.get("data", {})
        print(f"Current credentials keys: {list(current_creds.keys())}\n")

    # Try to inject client_id and client_secret
    response = requests.patch(
        f"{COMPOSIO_API}/connected_accounts/{account_id}",
        headers={
            "x-api-key": COMPOSIO_KEY,
            "Content-Type": "application/json"
        },
        json={
            "credentials": {
                "access_token": current_creds.get("access_token"),
                "refresh_token": current_creds.get("refresh_token"),
                # Try adding missing OAuth app credentials
                "client_id": "YOUR_GOOGLE_CLIENT_ID",
                "client_secret": "YOUR_GOOGLE_CLIENT_SECRET",
                "token_uri": "https://oauth2.googleapis.com/token"
            }
        }
    )

    print(f"Status: {response.status_code}")
    print(f"Response: {response.text[:500]}\n")

    if response.status_code in (200, 204):
        print("✓ SUCCESS: Can patch OAuth app credentials!")
        return True
    else:
        print("✗ FAILED: Cannot patch OAuth app credentials")
        return False


def main():
    if not COMPOSIO_KEY:
        print("❌ COMPOSIO_API_KEY not set")
        sys.exit(1)

    print("=" * 80)
    print("Testing Composio Manual Credential Management")
    print("=" * 80)
    print()

    # Test 1: Create with manual credentials
    account_id = test_manual_credential_creation()
    print()

    # Test 2: Update credentials (if creation succeeded)
    if account_id:
        test_credential_update(account_id)
        print()

    # Test 3: Fix existing broken account
    test_existing_account_update()

    print("=" * 80)
    print("CONCLUSION:")
    print("  If any test succeeded, you can use the hybrid approach!")
    print("  Otherwise, you must either:")
    print("    1. Fix auth config via Composio dashboard (1 hour)")
    print("    2. Build full self-hosted solution (3-6 months)")
    print("=" * 80)


if __name__ == "__main__":
    main()
