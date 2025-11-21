import asyncio
import json
import os
import sys
import traceback
from dotenv import load_dotenv

load_dotenv()

sys.path.append(os.getcwd())

from mcp_agent.core.context import AgentContext
from mcp_agent.registry.manager import RegistryManager


async def probe() -> None:
    user_id = "dev-local"
    ctx = AgentContext.create(user_id)
    registry = RegistryManager(ctx)

    print(f"\n--- PROBING GMAIL (User: {user_id}) ---")
    try:
        gmail_client = registry.get_mcp_client("gmail")
        print(f"DEBUG: Gmail URL -> {gmail_client.base_url}")

        res = await gmail_client.acall(
            "GMAIL_FETCH_EMAILS",
            {
                "query": "is:unread",
                "max_results": 1,
            },
        )
        print(json.dumps(res, indent=2))
    except Exception:
        traceback.print_exc()

    print(f"\n--- PROBING SLACK (User: {user_id}) ---")
    try:
        slack_client = registry.get_mcp_client("slack")
        print(f"DEBUG: Slack URL -> {slack_client.base_url}")

        res = await slack_client.acall(
            "SLACK_SEND_MESSAGE",
            {
                "channel": "#social",
                "text": "Test from probe script",
            },
        )
        print(json.dumps(res, indent=2))
    except Exception:
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(probe())
