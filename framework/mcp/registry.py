from dotenv import load_dotenv
from .mcp_client import MCPClient
from .oauth import OAuthManager
from framework.db.engine import session_scope
from framework.db.crud import get_active_mcp_for_provider
import os


MCP = {}
def init_registry(user_id: str | None = None):
    load_dotenv()
    uid = user_id or "singleton"

    # Rebuild known providers
    for prov in ["slack", "gmail"]:
        MCP.pop(prov, None)

    # DB-backed connections first (use OAuthManager.get_headers to merge x-api-key)
    with session_scope() as db:
        for prov in ("slack", "gmail"):
            url, _ = get_active_mcp_for_provider(db, uid, prov)
            if url:
                MCP[prov] = MCPClient(url, headers=OAuthManager.get_headers(uid, prov))

    # env fallback
    token = os.getenv("COMPOSIO_TOKEN", "")
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    slack_url_env = os.getenv("COMPOSIO_SLACK_URL")
    gmail_url_env = os.getenv("COMPOSIO_GMAIL_URL")
    if "slack" not in MCP and slack_url_env:
        MCP["slack"] = MCPClient(slack_url_env, headers=headers)
    if "gmail" not in MCP and gmail_url_env:
        MCP["gmail"] = MCPClient(gmail_url_env, headers=headers)

def is_registered(provider: str) -> bool:
    """Return True if a provider is present in the MCP registry."""
    return provider in MCP


def refresh_registry_from_oauth(user_id: str | None = None) -> None:
    """Refresh MCP clients based on stored OAuth connections."""
    init_registry(user_id)
