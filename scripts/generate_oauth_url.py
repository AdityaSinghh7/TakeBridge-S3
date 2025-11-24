#!/usr/bin/env python
from __future__ import annotations

import argparse
import sys

from mcp_agent.core.context import AgentContext
from mcp_agent.dev import resolve_dev_user
from mcp_agent.registry.oauth import AUTH_CONFIG_IDS, OAuthManager


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a Composio OAuth URL for a provider and user."
    )
    parser.add_argument(
        "--provider",
        "-p",
        required=True,
        help="Provider slug (e.g., shopify, github, slack).",
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

    auth_config = AUTH_CONFIG_IDS.get(provider) or ""
    if not auth_config:
        env_name = f"COMPOSIO_{provider.upper()}_AUTH_CONFIG_ID"
        sys.exit(f"Missing {env_name}; set it in your environment and retry.")

    try:
        url = OAuthManager.start_oauth(context, provider, redirect_uri="")
    except Exception as exc:  # pragma: no cover - CLI passthrough
        sys.exit(f"Failed to generate OAuth URL for provider '{provider}': {exc}")

    print(url)


if __name__ == "__main__":
    main()
