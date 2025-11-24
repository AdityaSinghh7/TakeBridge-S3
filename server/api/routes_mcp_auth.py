from fastapi import APIRouter, Request, HTTPException
from typing import Any, Optional
from fastapi.responses import JSONResponse, RedirectResponse
from urllib.parse import quote_plus

import os
from shared.db.engine import session_scope
from shared.db import crud
from mcp_agent.core.context import AgentContext
from mcp_agent.registry.oauth import (
    OAuthManager,
    COMPOSIO_HOST as _COMPOSIO_API_BASE,
    COMPOSIO_KEY as _COMPOSIO_KEY,
    COMPOSIO_API_V3 as _COMPOSIO_API_V3,
)
from mcp_agent.user_identity import normalize_user_id
from mcp_agent.knowledge.introspection import get_manifest as get_toolbox_manifest
from mcp_agent.knowledge.search import search_tools as toolbox_search_tools, list_providers as toolbox_list_providers
from mcp_agent.knowledge.utils import safe_filename
from shared.settings import build_redirect, OAUTH_REDIRECT_BASE
from mcp_agent.mcp_client import MCPClient
from computer_use_agent.tools.mcp_action_registry import sync_registered_actions


router = APIRouter(prefix="/api/mcp/auth", tags=["mcp-auth"])


def _require_user_id(request: Request) -> str:
    raw = (request.headers.get("X-User-Id") or "").strip()
    if not raw:
        raise HTTPException(400, "Missing X-User-Id header.")
    try:
        return normalize_user_id(raw)
    except ValueError as exc:
        raise HTTPException(400, str(exc))

def _normalize_provider(provider: str) -> str:
    return (provider or "").strip().lower()

def _attach_error(url: str | None, error_message: str) -> str | None:
    if not url:
        return None
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}error={quote_plus(error_message[:400])}"


@router.get("/{provider}/start")
def start(
    provider: str,
    request: Request,
    redirect_success: Optional[str] = None,
    redirect_error: Optional[str] = None,
):
    provider = _normalize_provider(provider)
    user_id = _require_user_id(request)
    context = AgentContext.create(user_id)
    # Build redirect deterministically from environment configuration
    redirect_uri = build_redirect(provider)
    try:
        # Hint redirect destinations for post-auth flows (optional)
        if redirect_success or redirect_error:
            OAuthManager.set_redirect_hints(
                provider,
                user_id,
                success_url=redirect_success,
                error_url=redirect_error,
            )

        url = OAuthManager.start_oauth(context, provider, redirect_uri)
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
    provider = _normalize_provider(provider)
    user_id = _require_user_id(request)
    context = AgentContext.create(user_id)
    qp = request.query_params
    ca_id = qp.get("connectedAccountId")
    status = qp.get("status")

    # Phase 2: finalize if Composio already redirected with connectedAccountId
    if ca_id:
        if status and status != "success":
            raise HTTPException(400, f"Composio reported status={status}")
        try:
            OAuthManager.finalize_connected_account(context, provider, ca_id)
            sync_registered_actions(user_id)
            redirect_url = OAuthManager.consume_redirect_hint(provider, user_id, success=True)
            target = redirect_url or f"/settings/integrations?connected={provider}"
            return RedirectResponse(url=target, status_code=302)
        except Exception as e:  # pragma: no cover - safety
            error_redirect = OAuthManager.consume_redirect_hint(provider, user_id, success=False)
            if error_redirect:
                target = _attach_error(error_redirect, str(e))
                if target:
                    return RedirectResponse(url=target, status_code=302)
            raise HTTPException(400, f"OAuth failed: {e}")

    # Phase 1: forward code/state to Composio's callback endpoint
    qs = request.url.query
    callback_url = f"{_COMPOSIO_API_V3}/toolkits/auth/callback"
    url = callback_url if not qs else f"{callback_url}?{qs}"
    return RedirectResponse(url=url, status_code=302)
    


@router.get("/providers")
def list_providers(request: Request):
    """List configured providers plus caller-specific authorization flags."""
    user_id = _require_user_id(request)
    summaries = toolbox_list_providers(user_id=user_id)
    providers: list[dict[str, Any]] = []
    for entry in summaries:
        prov = entry["provider"]
        env_key = f"COMPOSIO_{prov.upper()}_AUTH_CONFIG_ID"
        providers.append(
            {
                "provider": prov,
                "display_name": entry.get("display_name") or prov.capitalize(),
                "authorized": entry.get("authorized", False),
                "registered": entry.get("registered", False),
                "configured": entry.get("configured", False),
                "auth_config_present": bool(os.getenv(env_key)),
                "mcp_url": entry.get("mcp_url"),
                "tool_count": entry.get("tool_count", 0),
                "actions": entry.get("all_actions", []),
                "available_tools": entry.get("available_tools", []),
                "manifest_path": entry.get("path"),
            }
        )
    return {"providers": providers}


@router.get("/tools/available")
def available_tools(request: Request, provider: Optional[str] = None):
    """Surface detailed action metadata per provider for UI presentation."""
    user_id = _require_user_id(request)
    requested = _normalize_provider(provider) if provider else None
    manifest = get_toolbox_manifest(user_id=user_id)
    providers_out: list[dict[str, Any]] = []
    for prov in manifest.providers:
        if requested and prov.provider != requested:
            continue
        providers_out.append(
            {
                "provider": prov.provider,
                "authorized": prov.authorized,
                "registered": prov.registered,
                "configured": prov.configured,
                "mcp_url": prov.mcp_url,
                "actions": [
                    {
                        "name": tool.name,
                        "provider": prov.provider,
                        "description": tool.description,
                        "doc": tool.docstring,
                        "short_description": tool.short_description,
                        "available": tool.available,
                        "path": f"providers/{prov.provider}/tools/{safe_filename(tool.name)}.json",
                        "mcp_tool_name": tool.mcp_tool_name,
                    }
                    for tool in prov.actions
                ],
            }
        )
    if requested and not providers_out:
        raise HTTPException(404, f"Unknown provider '{provider}'")
    return {"providers": providers_out}


@router.get("/tools/search")
def search_tools(
    request: Request,
    q: Optional[str] = None,
    provider: Optional[str] = None,
    detail: str = "summary",
    limit: int = 20,
):
    user_id = _require_user_id(request)
    try:
        results = toolbox_search_tools(
            query=q,
            provider=provider,
            detail_level=detail,
            limit=limit,
            user_id=user_id,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return {"results": results, "detail_level": detail}


@router.get("/status")
def status(request: Request):
    user_id = _require_user_id(request)
    context = AgentContext.create(user_id)
    slack = OAuthManager.auth_status(context, "slack")
    gmail = OAuthManager.auth_status(context, "gmail")
    return {
        "slack": slack["authorized"],
        "gmail": gmail["authorized"],
        "details": {
            "slack": slack,
            "gmail": gmail,
        },
    }


@router.get("/{provider}/status/live")
def live_status(provider: str, request: Request):
    """Force-refresh provider status directly from Composio before responding."""
    provider = _normalize_provider(provider)
    user_id = _require_user_id(request)
    context = AgentContext.create(user_id)

    status = OAuthManager.auth_status(context, provider)
    status.update({"provider": provider})
    return status


@router.post("/{provider}/finalize")
def finalize(provider: str, payload: dict, request: Request):
    provider = _normalize_provider(provider)
    """Finalize a connected account manually (hosted link flows that skip callback).

    Body:
      - connected_account_id (str): e.g., "ca_..."
    """
    user_id = _require_user_id(request)
    context = AgentContext.create(user_id)
    ca_id = payload.get("connected_account_id") or payload.get("id") or payload.get("ca_id")
    if not ca_id:
        raise HTTPException(400, "connected_account_id is required")
    try:
        summary = OAuthManager.finalize_connected_account(context, provider, ca_id)
        # Registry is DB-backed, no manual refresh needed
        sync_registered_actions(user_id)
        return summary
    except Exception as e:
        raise HTTPException(400, f"Finalize failed: {e}")


@router.delete("/{provider}")
def disconnect(provider: str, request: Request, connected_account_id: str | None = None):
    provider = _normalize_provider(provider)
    """
    Disconnect a provider for the current user.

    Behavior:
      - If ?connected_account_id=... is supplied, only that CA is deactivated.
      - Else, all CAs for (user, provider) are deactivated.
      - Clears MCP URLs/headers so is_authorized() flips to False immediately.
    """
    user_id = _require_user_id(request)

    with session_scope() as db:
        if connected_account_id:
            summary = crud.disconnect_account(db, connected_account_id, user_id=user_id, provider=provider)
        else:
            summary = crud.disconnect_provider(db, user_id, provider)

    # Re-register actions (removes tools from ACI)
    # Registry is DB-backed, no manual refresh needed
    sync_registered_actions(user_id)

    return {"status": "disconnected", "provider": provider, **summary}


@router.get("/_debug/redirect/{provider}")
def debug_redirect(provider: str):
    """Debug helper to inspect the exact redirect URI constructed for a provider."""
    provider = _normalize_provider(provider)
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
                    prov = _normalize_provider(provider)
                    norm = [x for x in norm if (x.get("provider") or "").lower() == prov]
                return {"count": len(norm), "auth_configs": norm}
            last_err = f"HTTP {resp.status_code}: {resp.text[:300]}"
        except Exception as e:
            last_err = str(e)
    return {"status": "error", "error": last_err or "unknown"}


@router.get("/_debug/db")
def debug_db(request: Request):
    from shared.db.engine import session_scope
    from shared.db.models import User, ConnectedAccount, MCPConnection
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
    provider = _normalize_provider(provider)
    user_id = _require_user_id(request)
    context = AgentContext.create(user_id)
    url = OAuthManager.get_mcp_url(context, provider)
    hdrs = OAuthManager.get_headers(context, provider)
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
    user_id = _require_user_id(request)
    prov = _normalize_provider(provider)
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
