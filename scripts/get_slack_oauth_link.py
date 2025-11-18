"""
Get Slack OAuth authorization URL via the API endpoint.

Environment:
  SERVER_URL=https://localhost:8000 (default)
  USER_ID=dev-local

Usage:
  python scripts/get_slack_oauth_link.py

This script calls the /api/mcp/auth/slack/start endpoint to get an OAuth
authorization URL. Open the returned URL in your browser to authorize Slack.

After authorization, run:
  python scripts/generate_tool_output_schemas.py --user-id dev-local --providers slack --skip-unconfigured
"""

import os
import json
import sys
import requests
import urllib3

# Suppress SSL warnings for localhost self-signed certificates
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def main() -> int:
    base = os.getenv("SERVER_URL", "https://localhost:8000")
    user_id = os.getenv("USER_ID", "dev-local")
    url = f"{base.rstrip('/')}/api/mcp/auth/slack/start"

    print(f"Requesting Slack OAuth URL for user: {user_id}")
    print(f"Endpoint: {url}\n")

    # Disable SSL verification for localhost with self-signed certificates (default)
    verify_ssl = os.getenv("VERIFY_SSL", "false").lower() not in ("false", "0", "no", "off")
    if not verify_ssl and "localhost" in base:
        print("Note: SSL verification disabled for localhost (self-signed certificates)")
        print("Set VERIFY_SSL=true to enable verification\n")

    try:
        r = requests.get(
            url,
            headers={"X-User-Id": user_id},
            timeout=30,
            verify=verify_ssl,
        )
    except requests.exceptions.ConnectionError:
        print("ERROR: Could not connect to server.")
        print(f"Make sure the server is running at {base}")
        print("Start it with: uvicorn server.api.server:app --host 0.0.0.0 --port 8000 --reload --ssl-keyfile ./localhost+1-key.pem --ssl-certfile ./localhost+1.pem")
        return 1
    except requests.exceptions.SSLError as e:
        print("ERROR: SSL certificate verification failed.")
        print(f"This may be expected for localhost with self-signed certificates.")
        print(f"Detail: {e}")
        print("\nTo disable SSL verification (not recommended for production), modify the script.")
        return 1
    except requests.exceptions.Timeout:
        print("ERROR: Request timed out.")
        return 1
    except Exception as e:
        print(f"ERROR: Unexpected error: {e}")
        return 1

    print(f"Status: {r.status_code}")

    if r.status_code == 200:
        try:
            data = r.json()
            auth_url = data.get("authorization_url")
            if auth_url:
                print("\n" + "=" * 70)
                print("SUCCESS: Slack OAuth authorization URL:")
                print("=" * 70)
                print(auth_url)
                print("=" * 70)
                print("\nNext steps:")
                print("1. Open the URL above in your browser")
                print("2. Authorize Slack access")
                print("3. After authorization, run:")
                print(
                    "   python scripts/generate_tool_output_schemas.py "
                    f"--user-id {user_id} --providers slack --skip-unconfigured"
                )
                return 0
            else:
                print("ERROR: Response missing 'authorization_url' field")
                print(f"Response: {json.dumps(data, indent=2)}")
                return 1
        except json.JSONDecodeError:
            print("ERROR: Invalid JSON response")
            print(f"Response: {r.text[:500]}")
            return 1
    elif r.status_code == 400:
        print("ERROR: Bad request - missing or invalid user ID")
        print("Make sure X-User-Id header is set correctly")
        try:
            error_detail = r.json().get("detail", r.text)
            print(f"Detail: {error_detail}")
        except Exception:
            print(f"Response: {r.text[:500]}")
        return 1
    elif r.status_code == 502:
        print("ERROR: OAuth start failed")
        print("This usually means:")
        print("  - COMPOSIO_SLACK_AUTH_CONFIG_ID is not set")
        print("  - COMPOSIO_API_KEY is not set")
        print("  - Composio API is unreachable")
        try:
            error_detail = r.json().get("detail", r.text)
            print(f"\nDetail: {error_detail}")
        except Exception:
            print(f"\nResponse: {r.text[:500]}")
        return 1
    else:
        print(f"ERROR: Unexpected status code {r.status_code}")
        try:
            print(json.dumps(r.json(), indent=2))
        except Exception:
            print(f"Response: {r.text[:500]}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

