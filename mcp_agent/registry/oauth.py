"""OAuth management for MCP providers (debloated from mcp_agent/oauth.py).

Handles Composio OAuth flows, token management, and MCP URL generation.
Uses DB as source of truth - no in-memory state.
"""

from __future__ import annotations

import os
import time
from typing import TYPE_CHECKING, Any, Dict, List
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import requests

from mcp_agent.user_identity import normalize_user_id

from . import crud

if TYPE_CHECKING:
    from mcp_agent.core.context import AgentContext

# Composio API configuration
COMPOSIO_HOST = os.getenv(
    "COMPOSIO_API_BASE",
    os.getenv("COMPOSIO_BASE_URL", "https://backend.composio.dev")
).rstrip("/")
COMPOSIO_KEY = os.getenv("COMPOSIO_API_KEY", "")
COMPOSIO_API_V3 = f"{COMPOSIO_HOST}/api/v3"

# White-label redirect URL (on YOUR domain)
COMPOSIO_REDIRECT = os.getenv(
    "COMPOSIO_REDIRECT",
    "https://localhost:8000/api/composio-redirect",
)

# Map providers to Composio Auth Config IDs
AUTH_CONFIG_IDS = {
    "gmail": os.getenv("COMPOSIO_GMAIL_AUTH_CONFIG_ID", ""),
    "slack": os.getenv("COMPOSIO_SLACK_AUTH_CONFIG_ID", ""),
    "shopify": os.getenv("COMPOSIO_SHOPIFY_AUTH_CONFIG_ID", ""),
    "stripe": os.getenv("COMPOSIO_STRIPE_AUTH_CONFIG_ID", ""),
    "zendesk": os.getenv("COMPOSIO_ZENDESK_AUTH_CONFIG_ID", ""),
    "gorgias": os.getenv("COMPOSIO_GORGIAS_AUTH_CONFIG_ID", ""),
    "googledrive": os.getenv("COMPOSIO_GOOGLEDRIVE_AUTH_CONFIG_ID", ""),
    "airtable": os.getenv("COMPOSIO_AIRTABLE_AUTH_CONFIG_ID", ""),
    "amplitude": os.getenv("COMPOSIO_AMPLITUDE_AUTH_CONFIG_ID", ""),
    "apollo": os.getenv("COMPOSIO_APOLLO_AUTH_CONFIG_ID", ""),
    "calendly": os.getenv("COMPOSIO_CALENDLY_AUTH_CONFIG_ID", ""),
    "docusign": os.getenv("COMPOSIO_DOCUSIGN_AUTH_CONFIG_ID", ""),
    "dropbox": os.getenv("COMPOSIO_DROPBOX_AUTH_CONFIG_ID", ""),
    "figma": os.getenv("COMPOSIO_FIGMA_AUTH_CONFIG_ID", ""),
    "github": os.getenv("COMPOSIO_GITHUB_AUTH_CONFIG_ID", ""),
    "google_admin": os.getenv("COMPOSIO_GOOGLE_ADMIN_AUTH_CONFIG_ID", ""),
    "googlesheets": os.getenv("COMPOSIO_GOOGLESHEETS_AUTH_CONFIG_ID", ""),
    "googleslides": os.getenv("COMPOSIO_GOOGLESLIDES_AUTH_CONFIG_ID", ""),
    "intercom": os.getenv("COMPOSIO_INTERCOM_AUTH_CONFIG_ID", ""),
    "jira": os.getenv("COMPOSIO_JIRA_AUTH_CONFIG_ID", ""),
    "klaviyo": os.getenv("COMPOSIO_KLAVIYO_AUTH_CONFIG_ID", ""),
    "mailchimp": os.getenv("COMPOSIO_MAILCHIMP_AUTH_CONFIG_ID", ""),
    "notion": os.getenv("COMPOSIO_NOTION_AUTH_CONFIG_ID", ""),
    "pagerduty": os.getenv("COMPOSIO_PAGERDUTY_AUTH_CONFIG_ID", ""),
    "quickbooks": os.getenv("COMPOSIO_QUICKBOOKS_AUTH_CONFIG_ID", ""),
    "salesforce": os.getenv("COMPOSIO_SALESFORCE_AUTH_CONFIG_ID", ""),
    "snowflake": os.getenv("COMPOSIO_SNOWFLAKE_AUTH_CONFIG_ID", ""),
    "xero": os.getenv("COMPOSIO_XERO_AUTH_CONFIG_ID", ""),
}


def _headers() -> Dict[str, str]:
    """Get Composio API headers with API key."""
    if not COMPOSIO_KEY:
        raise RuntimeError("COMPOSIO_API_KEY missing")
    return {"x-api-key": COMPOSIO_KEY, "content-type": "application/json"}


def _require_auth_config(provider: str) -> str:
    """Get auth config ID for a provider, raising if not configured."""
    ac = AUTH_CONFIG_IDS.get(provider) or ""
    if not ac:
        raise RuntimeError(
            f"Missing COMPOSIO_*_AUTH_CONFIG_ID for provider={provider}"
        )
    return ac


class OAuthManager:
    """
    OAuth management for MCP providers via Composio.
    
    All methods now accept AgentContext for multi-tenant operations.
    DB is the source of truth - no in-memory state.
    """
    
    # In-memory redirect hints (optional)
    _redirect_hints: Dict[tuple[str, str], Dict[str, str | None]] = {}

    @classmethod
    def set_redirect_hints(
        cls, provider: str, user_id: str, *, success_url: str | None = None, error_url: str | None = None
    ) -> None:
        """Cache redirect hints for post-OAuth success/error redirects."""
        key = (normalize_user_id(user_id), provider.lower())
        cls._redirect_hints[key] = {"success": success_url, "error": error_url}

    @classmethod
    def consume_redirect_hint(cls, provider: str, user_id: str, success: bool) -> str | None:
        """Pop and return any cached redirect hint for this provider/user."""
        key = (normalize_user_id(user_id), provider.lower())
        hints = cls._redirect_hints.pop(key, None) or {}
        return hints.get("success" if success else "error")

    @classmethod
    def sync(cls, provider: str, user_id: str | Any, force: bool = False) -> None:
        """
        Compatibility no-op: legacy callers expect a sync hook.
        
        The current implementation persists OAuth state immediately during
        finalize, so no explicit sync is required.
        """
        return None

    @classmethod
    def auth_status(cls, context: "AgentContext", provider: str) -> Dict[str, Any]:
        """
        Compute provider auth status with refresh awareness.

        Returns:
            {
              "authorized": bool,
              "connected_account_id": str | None,
              "auth_config_id": str | None,
              "mcp_url": str | None,
              "refresh_required": bool,
              "reason": str | None,
            }
        """
        from mcp_agent.user_identity import normalize_user_id
        user_id = normalize_user_id(context.user_id)

        with context.get_db() as db:
            ca_id, ac_id, url, headers = crud.get_active_context_for_provider(db, user_id, provider)

        if not url or not ca_id:
            return {
                "authorized": False,
                "connected_account_id": ca_id,
                "auth_config_id": ac_id,
                "mcp_url": url,
                "refresh_required": False,
                "reason": "missing mcp_url" if not url else "missing connected_account_id",
            }

        refresh_required = False
        reason: str | None = None

        try:
            detail = _get_connected_account(ca_id)
            status = (detail.get("status") or "").upper()
            if status and status != "ACTIVE":
                refresh_required = True
                reason = f"connected_account_status={status}"
            if detail.get("auth_refresh_required"):
                refresh_required = True
                reason = reason or "auth_refresh_required"
        except Exception as exc:
            reason = f"status_check_failed: {exc}"

        authorized = bool(url and ca_id) and not refresh_required

        return {
            "authorized": authorized,
            "connected_account_id": ca_id,
            "auth_config_id": ac_id,
            "mcp_url": url,
            "refresh_required": refresh_required,
            "reason": reason,
        }
    
    @classmethod
    def start_oauth(
        cls,
        context: AgentContext,
        provider: str,
        redirect_uri: str,
        provider_fields: Dict[str, str] | None = None,
    ) -> str:
        """
        Initiate OAuth flow for a provider.
        
        Args:
            context: Agent context with user_id
            provider: Provider name ("gmail", "slack")
            redirect_uri: Ignored for white-label (uses COMPOSIO_REDIRECT)
            provider_fields: Optional provider-specific fields (e.g., Shopify subdomain)
        
        Returns:
            URL to redirect user to for OAuth consent
        """
        user_id = normalize_user_id(context.user_id)
        auth_config_id = _require_auth_config(provider)
        
        url = f"{COMPOSIO_API_V3}/connected_accounts"
        body = {
            "auth_config": {"id": auth_config_id},
            "connection": {
                "user_id": user_id,
                "callback_url": COMPOSIO_REDIRECT,
            },
        }

        # Provider-specific required fields
        provider_fields = provider_fields or {}
        field_map: Dict[str, str] = {}
        field_values: List[Dict[str, str]] = []
        seen_field_values: set[tuple[str, str, str]] = set()

        def _add_field(key: str | None, value: str | None) -> None:
            if not key or value is None or value == "":
                return
            field_map[key] = value
            for label in ("key", "name"):
                sig = (label, key, value)
                if sig not in seen_field_values:
                    field_values.append({label: key, "value": value})
                    seen_field_values.add(sig)

        if provider == "shopify":
            env_key = (os.getenv("SHOPIFY_STORE_FIELD_KEY") or "subdomain").strip() or "subdomain"
            shop_subdomain = (
                provider_fields.get("subdomain")
                or provider_fields.get("store_subdomain")
                or provider_fields.get(env_key)
                or os.getenv("SHOPIFY_STORE_SUBDOMAIN", "").strip()
            )
            if not shop_subdomain:
                raise RuntimeError(
                    "Shopify OAuth requires a store subdomain. "
                    "Provide it per-user (e.g., --shopify-subdomain or ?subdomain=...) "
                    "or set SHOPIFY_STORE_SUBDOMAIN for local development."
                )
            for key in {env_key, "subdomain", "store_subdomain"}:
                _add_field(key or "subdomain", shop_subdomain)

        # Attach any other provider-specific fields provided by caller
        for k, v in provider_fields.items():
            _add_field(k, v)

        if field_map:
            body["fields"] = field_map
            body["field_values"] = field_values
            body["connection"]["fields"] = field_map
            body["connection"]["field_values"] = field_values
            body["connection"]["state"] = {
                "authScheme": "OAUTH2",
                "val": {"status": "INITIALIZING", **field_map},
            }
            body["auth_config"]["fields"] = field_map
            body["auth_config"]["field_values"] = field_values
        
        try:
            r = requests.post(
                url,
                headers={**_headers(), "accept": "application/json"},
                json=body,
                timeout=20,
            )
        except requests.RequestException as e:
            raise RuntimeError(f"Composio API network error: {e}")
        
        if 200 <= r.status_code < 300 or r.status_code == 201:
            content_type = r.headers.get("content-type", "")
            data = r.json() if "application/json" in content_type else {}
            redirect_url = (
                data.get("redirect_url")
                or data.get("redirect_uri")
                or data.get("redirectUrl")
            )
            if not redirect_url:
                raise RuntimeError(
                    "Composio create-connected-account succeeded but no redirect URL returned."
                )
            return redirect_url
        
        snippet = r.text.strip()[:500]
        raise RuntimeError(f"Composio API error: HTTP {r.status_code} body={snippet}")
    
    @classmethod
    def finalize_connected_account(
        cls,
        context: AgentContext,
        provider: str,
        connected_account_id: str,
    ) -> Dict[str, Any]:
        """
        Finalize OAuth connection after callback.
        
        Polls until account is ACTIVE, generates MCP URL, persists to DB.
        
        Args:
            context: Agent context with user_id and db_session
            provider: Provider name
            connected_account_id: Composio connected account ID
        
        Returns:
            Dict with provider, connected_account_id, and mcp_url
        """
        user_id = normalize_user_id(context.user_id)
        
        # Wait for account to become ACTIVE
        detail = _wait_connected_account_active(connected_account_id)
        
        # Extract provider UID (email or team ID)
        provider_uid = (
            (detail.get("profile") or {}).get("email")
            or (detail.get("account") or {}).get("team_id")
            or detail.get("provider_uid")
        )
        
        # Verify auth config matches
        auth_cfg = detail.get("auth_config") or detail.get("authConfig") or {}
        auth_config_id = auth_cfg.get("id") or _require_auth_config(provider)
        expected_ac = _require_auth_config(provider)
        if auth_config_id and expected_ac and auth_config_id != expected_ac:
            raise RuntimeError(
                f"Connected account auth_config_id mismatch: "
                f"got={auth_config_id} expected={expected_ac}"
            )
        
        # Get or generate MCP URL
        mcp_info = (
            detail.get("mcp")
            or detail.get("mcp_server")
            or detail.get("mcpServer")
            or {}
        )
        mcp_url = (
            mcp_info.get("http_url")
            or mcp_info.get("url")
            or mcp_info.get("httpUrl")
        )
        mcp_headers = (
            mcp_info.get("headers")
            or mcp_info.get("http_headers")
            or mcp_info.get("httpHeaders")
            or {}
        )
        
        # Check if auth headers are present
        need_auth = True
        if mcp_headers:
            lk = {k.lower() for k in mcp_headers.keys()}
            need_auth = "authorization" not in lk
        
        # Generate token-bound URL if needed
        if not mcp_url or need_auth:
            server_id = _ensure_mcp_server(provider, auth_config_id)
            gen = _generate_mcp_url(server_id, user_id, connected_account_id)
            mcp_url = (
                gen.get("connected_mcp_url")
                or gen.get("mcp_url")
                or mcp_url
            )
            token = gen.get("mcp_token") or ""
            if token:
                mcp_headers = {
                    **(mcp_headers or {}),
                    "Authorization": f"Bearer {token}",
                }
        
        # Always include explicit CA header
        mcp_headers = {
            **(mcp_headers or {}),
            "X-Connected-Account-Id": connected_account_id,
        }
        
        # Ensure URL has binding params
        if mcp_url:
            mcp_url = _ensure_account_bound_url(mcp_url, user_id, connected_account_id)
        
        # Persist to DB
        with context.get_db() as db:
            crud.upsert_user(db, user_id)
            ac = detail.get("auth_config") or detail.get("authConfig") or {}
            ac_id = ac.get("id") or auth_config_id
            crud.upsert_auth_config(db, ac_id, provider, ac.get("name") or ac.get("label"))
            ca_row = crud.upsert_connected_account(
                db,
                connected_account_id,
                user_id,
                ac_id,
                provider,
                status=(detail.get("status") or "ACTIVE").upper(),
                provider_uid=provider_uid,
            )
            crud.upsert_mcp_connection(db, ca_row.id, mcp_url, mcp_headers, last_error=None)
        
        return {
            "provider": provider,
            "connected_account_id": connected_account_id,
            "mcp_url": mcp_url,
        }
    
    @classmethod
    def disconnect(cls, context: AgentContext, provider: str) -> None:
        """
        Disconnect a provider for the current user.
        
        Args:
            context: Agent context with user_id and db_session
            provider: Provider name
        """
        user_id = normalize_user_id(context.user_id)
        with context.get_db() as db:
            crud.disconnect_provider(db, user_id, provider)
    
    @classmethod
    def is_authorized(cls, context: AgentContext, provider: str) -> bool:
        """
        Check if user is authorized for a provider.
        
        Args:
            context: Agent context with user_id and db_session
            provider: Provider name
        
        Returns:
            True if user has active MCP connection
        """
        user_id = normalize_user_id(context.user_id)
        with context.get_db() as db:
            return crud.is_authorized(db, user_id, provider)
    
    @classmethod
    def get_mcp_url(cls, context: AgentContext, provider: str) -> str | None:
        """
        Get MCP URL for a provider.
        
        Args:
            context: Agent context with user_id and db_session
            provider: Provider name
        
        Returns:
            MCP URL or None if not connected
        """
        user_id = normalize_user_id(context.user_id)
        with context.get_db() as db:
            url, _ = crud.get_active_mcp_for_provider(db, user_id, provider)
            return url
    
    @classmethod
    def get_headers(cls, context: AgentContext, provider: str) -> Dict[str, str]:
        """
        Get HTTP headers for MCP requests.
        
        Includes auth tokens, connected account ID, and API key.
        Generates fresh token if Authorization header is missing.
        
        Args:
            context: Agent context with user_id and db_session
            provider: Provider name
        
        Returns:
            Dict of HTTP headers
        """
        user_id = normalize_user_id(context.user_id)
        with context.get_db() as db:
            ca_id, ac_id, _url, hdrs = crud.get_active_context_for_provider(
                db, user_id, provider
            )
            hdrs = (hdrs or {}).copy()
            
            # Check if Authorization header exists
            have_auth = any(k.lower() == "authorization" for k in hdrs.keys())
            
            # Generate fresh token if missing
            if ca_id and ac_id and not have_auth:
                try:
                    server_id = _ensure_mcp_server(provider, ac_id)
                    gen = _generate_mcp_url(server_id, user_id, ca_id)
                    token = gen.get("mcp_token") or ""
                    if token:
                        hdrs["Authorization"] = f"Bearer {token}"
                        # Persist updated headers
                        crud.upsert_mcp_connection(db, ca_id, _url, hdrs, last_error=None)
                except Exception:
                    pass  # Best effort
            
            # Fallback to env token if still no auth
            if not any(k.lower() == "authorization" for k in hdrs.keys()):
                env_token = os.getenv("COMPOSIO_TOKEN", "").strip()
                if env_token:
                    hdrs["Authorization"] = f"Bearer {env_token}"
            
            # Always include connected account ID
            if ca_id and not any(k.lower() == "x-connected-account-id" for k in hdrs.keys()):
                hdrs["X-Connected-Account-Id"] = ca_id
            
            # Include auth config hint
            if ac_id and not any(k.lower() == "x-auth-config-id" for k in hdrs.keys()):
                hdrs["X-Auth-Config-Id"] = ac_id
            
            # Merge static API key
            if COMPOSIO_KEY and not any(k.lower() == "x-api-key" for k in hdrs.keys()):
                hdrs["x-api-key"] = COMPOSIO_KEY
            
            return hdrs


# ----------------- Module-level helpers -----------------


def _get_connected_account(ca_id: str) -> Dict[str, Any]:
    """Fetch connected account details from Composio API."""
    r = requests.get(
        f"{COMPOSIO_API_V3}/connected_accounts/{ca_id}",
        headers=_headers(),
        timeout=15,  # Keep reasonable timeout - won't affect speed if Composio is working fine
    )
    r.raise_for_status()
    return r.json()


def _wait_connected_account_active(ca_id: str, timeout: int = 90) -> Dict[str, Any]:
    """Poll connected account until status is ACTIVE."""
    deadline = time.time() + timeout
    last: Dict[str, Any] = {}
    
    while time.time() < deadline:
        try:
            last = _get_connected_account(ca_id)
        except Exception:
            time.sleep(1)
            continue
        
        status = (last.get("status") or "").upper()
        if status == "ACTIVE":
            return last
        time.sleep(1)
    
    # Return last seen details for debugging
    return last


def _ensure_mcp_server(provider: str, auth_config_id: str) -> str:
    """
    Get or create an MCP server ID for this provider/auth_config.
    
    Args:
        provider: Provider name
        auth_config_id: Auth config ID
    
    Returns:
        MCP server ID
    """
    env_id = os.getenv("COMPOSIO_MCP_SERVER_ID", "").strip()
    if env_id:
        return env_id
    
    # Generate server name (Composio requires ^[a-zA-Z0-9- ]+$, 4-30 chars)
    prov_clean = "".join(c for c in provider if c.isalnum() or c == "-") or "prov"
    frag = "".join(c for c in auth_config_id if c.isalnum())[:6]
    base_name = f"tb-{prov_clean}-{frag}" if frag else f"tb-{prov_clean}"
    name = "".join(c for c in base_name if c.isalnum() or c in {" ", "-"})[:30]
    if len(name) < 4:
        name = "tb-srv1"
    
    # Try to create server
    r = requests.post(
        f"{COMPOSIO_API_V3}/mcp/servers",
        headers=_headers(),
        json={"name": name, "auth_config_ids": [auth_config_id]},
        timeout=20,
    )
    if r.status_code in (200, 201):
        data = r.json()
        srv_id = data.get("id") or data.get("server_id")
        if srv_id:
            return srv_id
    
    # Try to list and reuse by name
    try:
        r2 = requests.get(f"{COMPOSIO_API_V3}/mcp/servers", headers=_headers(), timeout=20)
        if 200 <= r2.status_code < 300:
            body = r2.json()
            items = body.get("items") or body.get("data") or body
            if isinstance(items, list):
                for s in items:
                    if (s.get("name") or "") == name:
                        sid = s.get("id") or s.get("server_id")
                        if sid:
                            return sid
    except Exception:
        pass
    
    # If all else fails, raise
    r.raise_for_status()
    raise RuntimeError("Unable to provision MCP server")


def _generate_mcp_url(server_id: str, user_id: str, ca_id: str) -> Dict[str, Any]:
    """
    Generate MCP URL for a server/user/connected_account.
    
    Args:
        server_id: MCP server ID
        user_id: User identifier
        ca_id: Connected account ID
    
    Returns:
        Dict with mcp_url, connected_mcp_url, and mcp_token
    """
    uid = normalize_user_id(user_id)
    r = requests.post(
        f"{COMPOSIO_API_V3}/mcp/servers/generate",
        headers=_headers(),
        json={
            "mcp_server_id": server_id,
            "user_ids": [uid],
            "connected_account_ids": [ca_id],
        },
        timeout=20,
    )
    r.raise_for_status()
    data = r.json()
    
    # Extract URL (prefer account-bound variant)
    base_url = data.get("mcp_url") or data.get("url") or None
    connected_url = None
    urls = data.get("connected_account_urls") or data.get("urls") or []
    
    if isinstance(urls, list):
        # Find URL containing this CA ID
        for u in urls:
            if isinstance(u, str) and ca_id in u:
                connected_url = u
                break
        if not connected_url and urls:
            connected_url = urls[0]
    elif isinstance(urls, dict):
        connected_url = urls.get(ca_id) or next(iter(urls.values()), None)
    
    # Extract token
    token = (
        data.get("mcp_token")
        or data.get("token")
        or data.get("mcpToken")
        or ""
    )
    
    if not token:
        catoks = (
            data.get("connected_account_tokens")
            or data.get("tokens")
            or data.get("connectedAccountTokens")
        )
        if isinstance(catoks, dict):
            token = catoks.get(ca_id) or next(iter(catoks.values()), "")
        elif isinstance(catoks, list) and catoks:
            for it in catoks:
                if not isinstance(it, dict):
                    continue
                if it.get("connected_account_id") == ca_id and it.get("token"):
                    token = it.get("token")
                    break
            if not token:
                first = catoks[0]
                if isinstance(first, dict):
                    token = first.get("token") or ""
    
    # Extract from headers if still missing
    if not token:
        hdrs = data.get("headers") or data.get("http_headers") or data.get("httpHeaders") or {}
        if isinstance(hdrs, dict):
            auth = hdrs.get("Authorization") or hdrs.get("authorization")
            if isinstance(auth, str) and auth.startswith("Bearer "):
                token = auth.split(" ", 1)[1]
    
    # Use connected URL as canonical if available
    chosen_url = connected_url or base_url
    if chosen_url:
        chosen_url = _ensure_account_bound_url(chosen_url, uid, ca_id)
    
    return {
        "mcp_url": chosen_url,
        "connected_mcp_url": connected_url,
        "mcp_token": token,
    }


def _ensure_account_bound_url(url: str, user_id: str, ca_id: str) -> str:
    """
    Ensure MCP URL includes binding query parameters.
    
    Adds/merges:
        - connected_account_ids=ca_id (overwrites if different)
        - user_id=user_id (overwrites if different)
    
    Args:
        url: Base MCP URL
        user_id: User identifier
        ca_id: Connected account ID
    
    Returns:
        URL with binding parameters
    """
    try:
        pr = urlparse(url)
        q = dict(parse_qsl(pr.query, keep_blank_values=True))
        # Always bind to the latest CA/user (refresh flows may reuse existing URLs)
        q["connected_account_ids"] = ca_id
        q["user_id"] = user_id
        new_q = urlencode(q)
        return urlunparse((pr.scheme, pr.netloc, pr.path, pr.params, new_q, pr.fragment))
    except Exception:
        return url
