#!/usr/bin/env python3
"""Fix Gmail authentication by re-connecting for dev-local user.

This script:
1. Disconnects the current Gmail connection (which has incomplete OAuth credentials)
2. Starts a new OAuth flow using Composio's managed auth
"""

import os
import sys
from pathlib import Path

# Add project root to path
repo_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(repo_root))

# Set PYTHONPATH for imports
os.environ['PYTHONPATH'] = str(repo_root)

def main():
    # Import here to avoid circular dependency issues
    from mcp_agent.core.context import AgentContext
    from mcp_agent.registry.oauth import OAuthManager

    context = AgentContext.create(user_id="dev-local", request_id="fix-auth")

    print("=== Step 1: Disconnecting old Gmail connection ===")
    try:
        OAuthManager.disconnect(context, "gmail")
        print("✓ Gmail disconnected for dev-local\n")
    except Exception as e:
        print(f"⚠ Warning: {e}\n")

    print("=== Step 2: Starting new OAuth flow ===")
    print("(This will use Composio's managed auth since COMPOSIO_GMAIL_AUTH_CONFIG_ID is now unset)")

    try:
        redirect_url = "https://localhost:8000/api/composio-redirect"
        oauth_url = OAuthManager.start_oauth(context, "gmail", redirect_url)

        print(f"\n🔗 OPEN THIS URL IN YOUR BROWSER:")
        print(f"\n{oauth_url}\n")
        print("=" * 80)
        print("\nAfter authorizing:")
        print("1. You'll be redirected to: https://localhost:8000/api/composio-redirect?...")
        print("2. Copy the entire redirect URL")
        print("3. Extract the 'connected_account_id' from the URL parameters")
        print("4. Run this to finalize:")
        print(f"\n    cd {repo_root}")
        print(f"    python3 -c 'from mcp_agent.core.context import AgentContext; from mcp_agent.registry.oauth import OAuthManager; ctx = AgentContext.create(user_id=\"dev-local\", request_id=\"finalize\"); result = OAuthManager.finalize_connected_account(ctx, \"gmail\", \"<CONNECTED_ACCOUNT_ID>\"); print(f\"✓ Gmail reconnected: {{result}}\")'")
        print("\n(Replace <CONNECTED_ACCOUNT_ID> with the actual ID from the redirect URL)")

    except Exception as e:
        print(f"❌ Error starting OAuth flow: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
