from fastapi import APIRouter, Request, HTTPException
from typing import Optional
from fastapi.responses import JSONResponse, RedirectResponse

from framework.mcp.oauth import (
    OAuthManager,
    COMPOSIO_HOST as _COMPOSIO_API_BASE,
    COMPOSIO_KEY as _COMPOSIO_KEY,
    COMPOSIO_API_V3 as _COMPOSIO_API_V3,
)
from framework.mcp.actions import register_mcp_actions
from framework.mcp.registry import refresh_registry_from_oauth
from framework.settings import build_redirect, OAUTH_REDIRECT_BASE
import os
from framework.db.engine import session_scope
from framework.db import crud
from framework.mcp.mcp_client import MCPClient


router = APIRouter(prefix="/api/mcp/auth", tags=["mcp-auth"])


@router.get("/{provider}/start")
def start(provider: str, request: Request):
    user_id = request.headers.get("X-User-Id", "singleton")
    # Build redirect deterministically from environment configuration
    redirect_uri = build_redirect(provider)
    try:
        url = OAuthManager.start_oauth(provider, user_id, redirect_uri)
        return JSONResponse({"authorization_url": url})
    except Exception as e:
        # Surface likely misconfig or connectivity problems clearly
        raise HTTPException(
            status_code=502,
            detail=(
                f"OAuth start failed: {e}. Check COMPOSIO_API_BASE, DNS/connectivity, and that your white-label"
                f" redirect (/api/composio-redirect) is configured in your Composio Auth Config."
            ),
        )


@router.get("/{provider}/callback", name="oauth_callback")
def callback(provider: str, request: Request, code: Optional[str] = None, state: Optional[str] = None):
    user_id = request.headers.get("X-User-Id", "singleton")
    try:
        OAuthManager.handle_callback(provider, user_id, code or "", state or "")
        # Pull latest connected account + MCP server details explicitly
        OAuthManager.sync(provider, user_id, force=True)
        # Make newly available clients & actions discoverable to Worker
        refresh_registry_from_oauth(user_id)
        register_mcp_actions()
        # Optional: redirect to your app UI success page
        return RedirectResponse(url=f"/settings/integrations?connected={provider}")
    except Exception as e:  # pragma: no cover - safety
        raise HTTPException(400, f"OAuth failed: {e}")


@router.get("/status")
def status(request: Request):
    user_id = request.headers.get("X-User-Id", "singleton")
    # Rehydrate from Composio on-demand so status survives restarts
    for prov in ("slack", "gmail"):
        try:
            OAuthManager.sync(prov, user_id, force=False)
        except Exception:
            pass
    return {
        "slack": OAuthManager.is_authorized("slack", user_id),
        "gmail": OAuthManager.is_authorized("gmail", user_id),
        # extend with other providers when enabled
    }


@router.post("/{provider}/finalize")
def finalize(provider: str, payload: dict, request: Request):
    """Finalize a connected account manually (hosted link flows that skip callback).

    Body:
      - connected_account_id (str): e.g., "ca_..."
    """
    user_id = request.headers.get("X-User-Id", "singleton")
    ca_id = payload.get("connected_account_id") or payload.get("id") or payload.get("ca_id")
    if not ca_id:
        raise HTTPException(400, "connected_account_id is required")
    try:
        summary = OAuthManager.finalize_connected_account(provider, user_id, ca_id)
        # Explicitly sync to fetch MCP connection details now that we know CA id
        OAuthManager.sync(provider, user_id, force=True)
        refresh_registry_from_oauth(user_id)
        register_mcp_actions()
        return summary
    except Exception as e:
        raise HTTPException(400, f"Finalize failed: {e}")


@router.delete("/{provider}")
def disconnect(provider: str, request: Request, connected_account_id: str | None = None):
    """
    Disconnect a provider for the current user.

    Behavior:
      - If ?connected_account_id=... is supplied, only that CA is deactivated.
      - Else, all CAs for (user, provider) are deactivated.
      - Clears MCP URLs/headers so is_authorized() flips to False immediately.
    """
    user_id = request.headers.get("X-User-Id", "singleton")

    with session_scope() as db:
        if connected_account_id:
            summary = crud.disconnect_account(db, connected_account_id, user_id=user_id, provider=provider)
        else:
            summary = crud.disconnect_provider(db, user_id, provider)

    # Clear in-memory registry + re-register actions (removes tools from ACI)
    refresh_registry_from_oauth(user_id)
    register_mcp_actions()

    return {"status": "disconnected", "provider": provider, **summary}


@router.get("/_debug/redirect/{provider}")
def debug_redirect(provider: str):
    """Debug helper to inspect the exact redirect URI constructed for a provider."""
    return {"redirect_uri": build_redirect(provider)}


@router.get("/_debug/config")
def debug_config():
    """Expose effective auth config (no secrets). Use for troubleshooting only."""
    return {
        "composio_api_base": _COMPOSIO_API_BASE,
        "has_composio_api_key": bool(_COMPOSIO_KEY),
        "has_gmail_auth_config_id": bool(os.getenv("COMPOSIO_GMAIL_AUTH_CONFIG_ID")),
        "oauth_redirect_base": OAUTH_REDIRECT_BASE,
        "redirect_example": build_redirect("gmail"),
        "api_v3": _COMPOSIO_API_V3,
    }


@router.get("/_debug/ping")
def debug_ping():
    """Attempt a simple call to Composio v3 to verify connectivity and key.

    Returns status and a small snippet of the upstream body.
    """
    import requests  # local import to avoid top-level side effects

    try:
        resp = requests.get(
            f"{_COMPOSIO_API_V3}/toolkits",
            headers={"x-api-key": os.getenv("COMPOSIO_API_KEY", "")},
            timeout=10,
        )
        body = resp.text[:500]
        return {"status": resp.status_code, "ok": resp.ok, "body_snippet": body}
    except Exception as e:
        return {"status": "error", "error": str(e)}


@router.get("/_debug/auth-configs")
def debug_auth_configs(provider: str | None = None):
    """List Auth Configs from Composio to locate the correct ac_* id.

    Optional query param `provider` can be a slug like 'gmail' to filter results client-side.
    """
    import requests  # local import

    headers = {"x-api-key": os.getenv("COMPOSIO_API_KEY", ""), "content-type": "application/json"}
    bases = [f"{_COMPOSIO_API_V3}/auth_configs", f"{_COMPOSIO_API_V3}/auth-configs"]
    last_err = None
    for url in bases:
        try:
            resp = requests.get(url, headers=headers, timeout=10)
            if 200 <= resp.status_code < 300:
                data = resp.json()
                items = data.get("items") or data.get("data") or data
                # Normalise to a simple list with id + provider
                norm = []
                for it in items:
                    norm.append(
                        {
                            "id": it.get("id") or it.get("auth_config_id"),
                            "name": it.get("name") or it.get("label") or it.get("title"),
                            "provider": (it.get("toolkit") or it.get("app") or {}).get("slug") or it.get("app_slug"),
                        }
                    )
                if provider:
                    norm = [x for x in norm if (x.get("provider") or "").lower() == provider.lower()]
                return {"count": len(norm), "auth_configs": norm}
            last_err = f"HTTP {resp.status_code}: {resp.text[:300]}"
        except Exception as e:
            last_err = str(e)
    return {"status": "error", "error": last_err or "unknown"}


@router.get("/_debug/db")
def debug_db(request: Request):
    from framework.db.engine import session_scope
    from framework.db.models import User, ConnectedAccount, MCPConnection
    with session_scope() as db:
        users = db.query(User).count()
        cas = db.query(ConnectedAccount).count()
        mcp = db.query(MCPConnection).count()
    return {"users": users, "connected_accounts": cas, "mcp_connections": mcp}


def _redact_headers(h: dict) -> dict:
    out = {}
    for k, v in (h or {}).items():
        kl = k.lower()
        if kl == "authorization" and isinstance(v, str):
            out[k] = v.split(" ")[0] + " *****"
        elif kl in ("x-api-key", "x-api-key".lower()) and isinstance(v, str):
            out[k] = v[:4] + "*****"
        else:
            out[k] = v
    return out


@router.get("/_debug/mcp_client")
def debug_mcp_client(request: Request, provider: str, test_tool: str | None = None):
    """Inspect the MCP client that will be used for a provider.

    Query params:
      - provider: gmail|slack
      - test_tool: optional tool name to invoke with empty args
    """
    user_id = request.headers.get("X-User-Id", "singleton")
    url = OAuthManager.get_mcp_url(user_id, provider)
    hdrs = OAuthManager.get_headers(user_id, provider)
    if not url:
        return {"ok": False, "error": "no mcp_url", "provider": provider}
    client = MCPClient(url, headers=hdrs)
    tools = []
    try:
        tools = client.list_tools()
    except Exception as e:
        tools = [f"<list-tools failed: {e}>"]
    out = {"ok": True, "provider": provider, "url": url, "headers": _redact_headers(hdrs), "tools": tools}
    if test_tool:
        try:
            out["test_call"] = client.call(test_tool, {})
        except Exception as e:
            out["test_call"] = {"status": "error", "error": str(e)}
    return out


@router.get("/_debug/connected-accounts")
def debug_connected_accounts(request: Request, provider: str):
    """List raw connected accounts from Composio for a provider + user.

    Query params:
      - provider: e.g. 'gmail' or 'slack'
    Uses X-User-Id header for the user filter and env for auth_config id.
    """
    import requests
    user_id = request.headers.get("X-User-Id", "singleton")
    prov = (provider or "").lower()
    ac_env = f"COMPOSIO_{prov.upper()}_AUTH_CONFIG_ID"
    ac_id = os.getenv(ac_env, "")
    if not ac_id:
        return {"ok": False, "error": f"missing {ac_env}"}
    headers = {"x-api-key": os.getenv("COMPOSIO_API_KEY", ""), "content-type": "application/json"}
    bases = [f"{_COMPOSIO_API_V3}/connected_accounts", f"{_COMPOSIO_API_V3}/connected-accounts"]
    last_err = None
    for url in bases:
        try:
            resp = requests.get(url, headers=headers, params={"user_id": user_id, "auth_config_id": ac_id}, timeout=15)
            if 200 <= resp.status_code < 300:
                data = resp.json()
                items = data.get("items") or data.get("data") or []
                # Normalize a compact view
                out = []
                for it in items:
                    out.append({
                        "id": it.get("id") or it.get("connected_account_id"),
                        "user_id": it.get("user_id") or ((it.get("connection") or {}).get("user_id")),
                        "status": (it.get("status") or "").upper(),
                        "provider_uid": (it.get("profile") or {}).get("email") or (it.get("account") or {}).get("team_id"),
                    })
                return {"ok": True, "count": len(out), "items": out, "auth_config_id": ac_id, "provider": prov}
            last_err = f"HTTP {resp.status_code}: {resp.text[:300]}"
        except Exception as e:
            last_err = str(e)
    return {"ok": False, "error": last_err or "unknown", "auth_config_id": ac_id, "provider": prov}
