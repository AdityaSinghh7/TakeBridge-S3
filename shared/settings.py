import os

# Canonical base for building OAuth callback URLs.
# Example values:
#   local dev:  "http://localhost:8000"
#   production: "https://app.yourdomain.com"
OAUTH_REDIRECT_BASE = os.getenv("OAUTH_REDIRECT_BASE", "http://localhost:8000").rstrip("/")


def build_redirect(provider: str) -> str:
    """Build deterministic OAuth redirect URL for a provider.

    This avoids deriving scheme/host/port from inbound requests which may be
    inconsistent when behind proxies or using different hosts.
    """
    return f"{OAUTH_REDIRECT_BASE}/api/mcp/auth/{provider}/callback"

