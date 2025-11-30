#!/usr/bin/env python
from __future__ import annotations

import argparse
import sys

from mcp_agent.core.context import AgentContext
from mcp_agent.dev import resolve_dev_user
from mcp_agent.registry.oauth import OAuthManager


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Disconnect a provider OAuth connection for a user."
    )
    parser.add_argument(
        "--provider",
        "-p",
        required=True,
        help="Provider slug (e.g., mailchimp, shopify, github, slack).",
    )
    parser.add_argument(
        "--user-id",
        help="Optional user id (defaults to dev-local resolution).",
        default=None,
    )
    args = parser.parse_args()

    provider = args.provider.strip().lower()
    user_id = resolve_dev_user(args.user_id)
    context = AgentContext.create(user_id=user_id)

    try:
        OAuthManager.disconnect(context, provider)
        print(f"Successfully disconnected {provider} for user {user_id}")
    except Exception as exc:
        sys.exit(f"Failed to disconnect provider '{provider}': {exc}")


if __name__ == "__main__":
    main()

