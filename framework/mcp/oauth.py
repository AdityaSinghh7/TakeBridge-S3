from __future__ import annotations

import os
import time
import typing as t
import requests
from urllib.parse import urlparse, parse_qsl, urlencode, urlunparse
from framework.db.engine import session_scope
from framework.db import crud

# ---- Composio API base + key ----
COMPOSIO_HOST = os.getenv("COMPOSIO_API_BASE", os.getenv("COMPOSIO_BASE_URL", "https://backend.composio.dev")).rstrip("/")
COMPOSIO_KEY = os.getenv("COMPOSIO_API_KEY", "")
COMPOSIO_API_V3 = f"{COMPOSIO_HOST}/api/v3"

# ---- White-label redirect on YOUR domain ----
# This is the URL you will put in the Google OAuth client (and in Composio Auth Config).
# It MUST exist on YOUR domain and forward to Composio's callback.
COMPOSIO_REDIRECT = os.getenv(
    "COMPOSIO_REDIRECT",
    "https://localhost:8000/api/composio-redirect",
)

# ---- Map providers -> Composio Auth Config IDs (created in Composio dashboard) ----
# For single-user now, put values directly in env. Later you can store per-tenant.
AUTH_CONFIG_IDS = {
    "gmail": os.getenv("COMPOSIO_GMAIL_AUTH_CONFIG_ID", ""),
    "slack": os.getenv("COMPOSIO_SLACK_AUTH_CONFIG_ID", ""),
}

# ---- Simple in-memory store for single user (expand to DB later) ----
# Shape:
#   _store[user_id][provider] = {
#       "connected_account_id": "ca_...",
#       "mcp_url": "https://.../mcp/http/...",
#       "mcp_headers": {"Header": "Value", ...},
#       "last_sync": 1730000000.0
#   }
_store: dict[str, dict[str, dict[str, t.Any]]] = {}


def _headers() -> dict[str, str]:
    if not COMPOSIO_KEY:
        raise RuntimeError("COMPOSIO_API_KEY missing")
    return {"x-api-key": COMPOSIO_KEY, "content-type": "application/json"}


def _require_auth_config(provider: str) -> str:
    ac = AUTH_CONFIG_IDS.get(provider) or ""
    if not ac:
        raise RuntimeError(f"Missing COMPOSIO_*_AUTH_CONFIG_ID for provider={provider}")
    return ac


def _ensure_user(user_id: str) -> None:
    if user_id not in _store:
        _store[user_id] = {}


class OAuthManager:
    """
    White-label OAuth via Composio:
      - We initiate a connection request (gives us a redirect URL to send the user to).
      - The provider redirects BACK to our branded endpoint (/api/composio-redirect).
      - Our branded endpoint forwards params to Composio's callback.
      - After Composio finalizes, we 'sync' to fetch the Connected Account + MCP server info.
    """

    # ----------------- High-level helpers used by your app -----------------

    @classmethod
    def start_oauth(cls, provider: str, user_id: str, redirect_uri: str) -> str:
        """
        Initiate an OAuth connection for `provider` and return a URL to redirect the user to.
        `redirect_uri` is ignored here for white-label; we always use COMPOSIO_REDIRECT
        in the Composio Auth Config itself.
        """
        user_id = user_id or "singleton"
        auth_config_id = _require_auth_config(provider)

        url = f"{COMPOSIO_API_V3}/connected_accounts"

        body = {
            "auth_config": {"id": auth_config_id},
            "connection": {
                "user_id": user_id,
                # Preferred per docs for white-label flows
                "callback_url": COMPOSIO_REDIRECT,
            },
        }

        try:
            r = requests.post(
                url,
                headers={**_headers(), "accept": "application/json"},
                json=body,
                timeout=20,
            )
        except requests.RequestException as e:
            raise RuntimeError(f"network error: {e}")

        if 200 <= r.status_code < 300 or r.status_code == 201:
            content_type = r.headers.get("content-type", "")
            data = r.json() if "application/json" in content_type else {}
            redirect = data.get("redirect_url") or data.get("redirect_uri") or data.get("redirectUrl")
            if not redirect:
                raise RuntimeError("Composio create-connected-account succeeded but no redirect URL returned.")
            return redirect

        snippet = r.text.strip()[:500]
        raise RuntimeError(f"HTTP {r.status_code} {url} body={snippet}")

    @classmethod
    def handle_callback(cls, provider: str, user_id: str, code: str, state: str) -> None:
        """
        With white-label, the provider is NOT calling this route.
        Our branded endpoint forwards directly to Composio's callback.
        This method is kept for backwards compatibility and no-ops.
        """
        return

    @classmethod
    def finalize_connected_account(cls, provider: str, user_id: str, connected_account_id: str) -> dict:
        """
        For hosted-link flows: we already have the connected account id from the
        Composio redirect. Make sure the account is ACTIVE, then obtain an MCP URL
        either from the account details or by generating one via the MCP servers API.
        Persist the MCP details into memory for this single-user setup.
        """
        user_id = user_id or "singleton"
        _ensure_user(user_id)

        # 1) Poll the connected account until ACTIVE, then fetch details
        detail = _wait_connected_account_active(connected_account_id)

        # Normalize provider_uid/email/teamid for debugging
        provider_uid = (detail.get("profile") or {}).get("email") \
            or (detail.get("account") or {}).get("team_id") \
            or detail.get("provider_uid")

        # Defensive: ensure the connected account actually belongs to this provider's auth config
        auth_cfg = detail.get("auth_config") or detail.get("authConfig") or {}
        auth_config_id = auth_cfg.get("id") or _require_auth_config(provider)
        expected_ac = _require_auth_config(provider)
        if auth_config_id and expected_ac and auth_config_id != expected_ac:
            raise RuntimeError(
                f"Connected account auth_config_id mismatch: got={auth_config_id} expected={expected_ac}. "
                f"Did you call finalize for the wrong provider?"
            )

        # 2) Try to get MCP details directly from the account, if present
        mcp_info = (detail.get("mcp") or detail.get("mcp_server") or detail.get("mcpServer") or {}) or {}
        mcp_url = mcp_info.get("http_url") or mcp_info.get("url") or mcp_info.get("httpUrl")
        mcp_headers = mcp_info.get("headers") or mcp_info.get("http_headers") or mcp_info.get("httpHeaders") or {}

        # 3) Ensure an MCP URL + auth are present. If URL missing OR no auth header,
        #    generate a token-bound URL for this CA and attach Authorization.
        need_auth = True
        if mcp_headers:
            lk = {k.lower() for k in mcp_headers.keys()}
            need_auth = ("authorization" not in lk)
        if not mcp_url or need_auth:
            server_id = _ensure_mcp_server(provider, auth_config_id)
            gen = _generate_mcp_url(server_id, user_id, connected_account_id)
            # Prefer account-bound URL with required query params
            mcp_url = gen.get("connected_mcp_url") or gen.get("mcp_url") or mcp_url
            token = gen.get("mcp_token") or ""
            if token:
                mcp_headers = {**(mcp_headers or {}), "Authorization": f"Bearer {token}"}
        # Always include an explicit CA header for downstream binding (defensive)
        mcp_headers = {**(mcp_headers or {}), "X-Connected-Account-Id": connected_account_id}

        # Ensure URL explicitly carries binding params (?connected_account_ids=...&user_id=...)
        if mcp_url:
            mcp_url = _ensure_account_bound_url(mcp_url, user_id, connected_account_id)

        # 4) Persist to DB (source of truth)
        with session_scope() as db:
            # upsert users/auth configs/CA
            crud.upsert_user(db, user_id)
            ac = detail.get("auth_config") or detail.get("authConfig") or {}
            ac_id = ac.get("id") or _require_auth_config(provider)
            crud.upsert_auth_config(db, ac_id, provider, ac.get("name") or ac.get("label"))
            ca_row = crud.upsert_connected_account(
                db, connected_account_id, user_id, ac_id, provider,
                status=(detail.get("status") or "ACTIVE").upper(),
                provider_uid=provider_uid
            )
            # Always use the DB CA id (may differ if a prior row exists for this user+auth_config)
            crud.upsert_mcp_connection(db, ca_row.id, mcp_url, mcp_headers, last_error=None)

        # Keep lightweight cache for quick TTL-based sync throttling
        _store[user_id][provider] = {
            "connected_account_id": connected_account_id,
            "mcp_url": mcp_url,
            "mcp_headers": mcp_headers or {},
            "last_sync": time.time(),
        }
        return {"provider": provider, "connected_account_id": connected_account_id, "mcp_url": mcp_url}

    @classmethod
    def disconnect(cls, provider: str, user_id: str) -> None:
        user_id = user_id or "singleton"
        # Also clear DB, not just memory
        with session_scope() as db:
            crud.disconnect_provider(db, user_id, provider)
        if user_id in _store:
            _store[user_id].pop(provider, None)

    @classmethod
    def is_authorized(cls, provider: str, user_id: str | None = None) -> bool:
        user_id = user_id or "singleton"
        with session_scope() as db:
            return crud.is_authorized(db, user_id, provider)

    # ----------------- MCP connection exposure to your registry -----------------

    @classmethod
    def get_mcp_url(cls, user_id: str, provider: str) -> str | None:
        with session_scope() as db:
            url, _ = crud.get_active_mcp_for_provider(db, user_id or "singleton", provider)
            return url

    @classmethod
    def get_headers(cls, user_id: str, provider: str) -> dict[str, str]:
        uid = user_id or "singleton"
        with session_scope() as db:
            ca_id, ac_id, _url, hdrs = crud.get_active_context_for_provider(db, uid, provider)
            hdrs = (hdrs or {}).copy()
            have_auth = any(k.lower() == "authorization" for k in hdrs.keys())
            # If Authorization is missing but we have an active CA + auth_config, generate a fresh token
            if ca_id and ac_id and not have_auth:
                try:
                    server_id = _ensure_mcp_server(provider, ac_id)
                    gen = _generate_mcp_url(server_id, uid, ca_id)
                    token = gen.get("mcp_token") or ""
                    if token:
                        hdrs["Authorization"] = f"Bearer {token}"
                        # persist the updated headers
                        crud.upsert_mcp_connection(db, ca_id, _url, hdrs, last_error=None)
                except Exception:
                    pass
            # Fallback: if still no Authorization, but COMPOSIO_TOKEN is present, attach it
            if not any(k.lower() == "authorization" for k in hdrs.keys()):
                env_token = os.getenv("COMPOSIO_TOKEN", "").strip()
                if env_token:
                    hdrs["Authorization"] = f"Bearer {env_token}"
            # Always attach connected account id as an explicit hint
            if ca_id and not any(k.lower() == "x-connected-account-id" for k in hdrs.keys()):
                hdrs["X-Connected-Account-Id"] = ca_id
            # Also include auth_config hint if known (defensive)
            if ac_id and not any(k.lower() == "x-auth-config-id" for k in hdrs.keys()):
                hdrs["X-Auth-Config-Id"] = ac_id
            # Merge static x-api-key
            if COMPOSIO_KEY and not any(k.lower() == "x-api-key" for k in hdrs.keys()):
                hdrs["x-api-key"] = COMPOSIO_KEY
            return hdrs

    @classmethod
    def sync(cls, provider: str, user_id: str, force: bool = False) -> None:
        """Explicit sync to be called after OAuth completes (no import-time network)."""
        cls._sync_connection(provider, user_id, force=force)

    # ----------------- Internal: fetch/refresh connection + MCP details -----------------

    @classmethod
    def _sync_connection(cls, provider: str, user_id: str, force: bool = False) -> None:
        """
        Fetch the latest Connected Account + MCP HTTP server details from Composio
        and cache them in memory. For single-user, this is fine; later back with DB.
        """
        user_id = user_id or "singleton"
        _ensure_user(user_id)

        slot = _store[user_id].get(provider, {})
        last = slot.get("last_sync", 0.0)
        if not force and (time.time() - last) < 30 and slot.get("mcp_url"):
            return  # fresh enough

        auth_config_id = _require_auth_config(provider)

        # Helper: safe GET that treats 404/network errors as "not connected yet"
        def _safe_get(url: str, **kw):
            try:
                r = requests.get(url, headers=_headers(), timeout=15, **kw)
                if r.status_code == 404:
                    return None
                r.raise_for_status()
                return r
            except requests.RequestException:
                return None

        # Determine which connected account ID to use. If we already know one,
        # prefer it; otherwise list accounts for THIS user + auth_config.
        existing_ca_id = slot.get("connected_account_id")
        ca_id = None
        detail = None  # ensure defined; avoids UnboundLocalError when we set later
        if existing_ca_id:
            ca_id = existing_ca_id
        else:
            list_urls = [
                f"{COMPOSIO_API_V3}/connected_accounts",
                f"{COMPOSIO_API_V3}/connected-accounts",
            ]
            r = None
            for url in list_urls:
                r = _safe_get(url, params={"user_id": user_id, "auth_config_id": auth_config_id})
                if r is not None:
                    break
            if r is None:
                return  # not connected/reachable yet

            body = r.json()
            items = body.get("items") or body.get("data") or []
            if not items:
                return  # not connected yet

            # Choose the item that belongs to this user (defensive to field shapes)
            def _uid(x: dict) -> str | None:
                if not isinstance(x, dict):
                    return None
                return x.get("user_id") or ((x.get("connection") or {}).get("user_id"))

            def _item_ac_id(x: dict) -> str | None:
                if not isinstance(x, dict):
                    return None
                ac = x.get("auth_config") or x.get("authConfig") or {}
                return ac.get("id")

            # Filter both by user and by the intended auth_config_id to avoid cross-provider leakage
            candidates = [x for x in items if _uid(x) == user_id and (_item_ac_id(x) == auth_config_id or _item_ac_id(x) is None)]
            if not candidates:
                return  # nothing for this user

            # Prefer an ACTIVE connected account for this user
            ca_id = None
            detail = None
            for ca in candidates:
                _cid = ca.get("id") or ca.get("connected_account_id")
                if not _cid:
                    continue
                # Peek detail to verify status
                for durl in (
                    f"{COMPOSIO_API_V3}/connected_accounts/{_cid}",
                    f"{COMPOSIO_API_V3}/connected-accounts/{_cid}",
                ):
                    r_ = _safe_get(durl)
                    if r_ is None:
                        continue
                    detail_ = r_.json()
                    # Drop if the connected account does not belong to this provider's auth_config
                    det_ac = (detail_.get("auth_config") or detail_.get("authConfig") or {}).get("id")
                    if det_ac and det_ac != auth_config_id:
                        continue
                    if (detail_.get("status") or "").upper() == "ACTIVE":
                        ca_id = _cid
                        detail = detail_
                        break
                if ca_id:
                    break
            if not ca_id:
                return  # no ACTIVE account yet for this user

        # 2) Get connection details (including MCP server info) for that connected account.
        detail_urls = [
            f"{COMPOSIO_API_V3}/connected_accounts/{ca_id}",
            f"{COMPOSIO_API_V3}/connected-accounts/{ca_id}",
        ]
        r2 = None
        for url in detail_urls:
            r2 = _safe_get(url)
            if r2 is not None:
                break
        if r2 is None:
            return
        # If we already fetched detail when choosing an ACTIVE candidate above,
        # reuse it; otherwise use the response we just fetched.
        detail = detail or r2.json()
        # Require ACTIVE status for caching/usage
        status = (detail.get("status") or "").upper()
        if status != "ACTIVE":
            return

        # Normalize likely fields (Composio provides an MCP HTTP server for the account).
        mcp_info = (
            detail.get("mcp") or
            detail.get("mcp_server") or
            detail.get("mcpServer") or
            {}
        )
        mcp_url = (
            mcp_info.get("http_url") or
            mcp_info.get("url") or
            mcp_info.get("httpUrl")
        )
        mcp_headers = (
            mcp_info.get("headers") or
            mcp_info.get("http_headers") or
            mcp_info.get("httpHeaders") or
            {}
        )

        # If no MCP URL came back OR no auth headers, ensure a server exists and generate now
        auth_cfg = detail.get("auth_config") or detail.get("authConfig") or {}
        auth_config_id = auth_cfg.get("id") or _require_auth_config(provider)
        need_auth = True
        if mcp_headers:
            lk = {k.lower() for k in mcp_headers.keys()}
            need_auth = ("authorization" not in lk)
        if not mcp_url or need_auth:
            server_id = _ensure_mcp_server(provider, auth_config_id)
            gen = _generate_mcp_url(server_id, user_id, ca_id)
            # Prefer account-bound URL with required query params
            mcp_url = gen.get("connected_mcp_url") or gen.get("mcp_url") or mcp_url
            token = gen.get("mcp_token") or ""
            if token:
                mcp_headers = {**(mcp_headers or {}), "Authorization": f"Bearer {token}"}
        # Include explicit CA header (defensive)
        mcp_headers = {**(mcp_headers or {}), "X-Connected-Account-Id": ca_id}

        # Ensure URL explicitly carries binding params (?connected_account_ids=...&user_id=...)
        if mcp_url:
            mcp_url = _ensure_account_bound_url(mcp_url, user_id, ca_id)

        # Persist to DB as source of truth
        with session_scope() as db:
            crud.upsert_user(db, user_id)
            ac = detail.get("auth_config") or detail.get("authConfig") or {}
            ac_id = ac.get("id") or _require_auth_config(provider)
            crud.upsert_auth_config(db, ac_id, provider, ac.get("name") or ac.get("label"))
            ca_row = crud.upsert_connected_account(
                db, ca_id, user_id, ac_id, provider,
                status=(detail.get("status") or "").upper() or "ACTIVE",
                provider_uid=(detail.get("profile") or {}).get("email") or (detail.get("account") or {}).get("team_id"),
            )
            # Use DB CA id (may differ due to unique (user, auth_config))
            crud.upsert_mcp_connection(db, ca_row.id, mcp_url, mcp_headers, last_error=None)

        # Lightweight cache for rate-limiting external calls
        _store[user_id][provider] = {
            "connected_account_id": ca_id,
            "mcp_url": mcp_url,
            "mcp_headers": mcp_headers or {},
            "last_sync": time.time(),
        }


# ----------------- Module-level helpers for MCP server generation -----------------

def _get_connected_account(ca_id: str) -> dict:
    r = requests.get(
        f"{COMPOSIO_API_V3}/connected_accounts/{ca_id}", headers=_headers(), timeout=15
    )
    r.raise_for_status()
    return r.json()


def _wait_connected_account_active(ca_id: str, timeout: int = 90) -> dict:
    """Poll the connected account until status == ACTIVE; return details."""
    deadline = time.time() + timeout
    last: dict = {}
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
    # Return the last seen details to aid debugging
    return last


def _ensure_mcp_server(provider: str, auth_config_id: str) -> str:
    """Return an MCP server id. Use env if provided; else create or reuse.

    Composio requires name to match ^[a-zA-Z0-9- ]+$ and be 4-30 chars.
    """
    env_id = os.getenv("COMPOSIO_MCP_SERVER_ID", "").strip()
    if env_id:
        return env_id

    prov_clean = "".join(c for c in provider if c.isalnum() or c == "-") or "prov"
    frag = "".join(c for c in auth_config_id if c.isalnum())[:6]
    base_name = f"tb-{prov_clean}-{frag}" if frag else f"tb-{prov_clean}"
    name = "".join(c for c in base_name if c.isalnum() or c in {" ", "-"})[:30]
    if len(name) < 4:
        name = "tb-srv1"
    # Try create
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
    # Try list and reuse by name
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
    # If creation failed, raise the original response
    r.raise_for_status()
    raise RuntimeError("Unable to provision MCP server")


def _generate_mcp_url(server_id: str, user_id: str, ca_id: str) -> dict:
    """Generate an MCP URL for a given server+user+connected account."""
    r = requests.post(
        f"{COMPOSIO_API_V3}/mcp/servers/generate",
        headers=_headers(),
        json={
            "mcp_server_id": server_id,
            "user_ids": [user_id or "singleton"],
            "connected_account_ids": [ca_id],
        },
        timeout=20,
    )
    r.raise_for_status()
    data = r.json()
    # Normalize: prefer account-bound URL when present
    base_url = (
        data.get("mcp_url")
        or data.get("url")
        or None
    )
    connected_url = None
    urls = data.get("connected_account_urls") or data.get("urls") or []
    if isinstance(urls, list):
        # Pick URL that contains this CA id if possible
        for u in urls:
            if isinstance(u, str) and ca_id in u:
                connected_url = u
                break
        if not connected_url and urls:
            connected_url = urls[0]
    elif isinstance(urls, dict):
        connected_url = urls.get(ca_id) or next(iter(urls.values()), None)

    # Token may be under various keys; also allow CA-specific collections
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
            # list of {'connected_account_id': 'ca_..', 'token': '...'}
            for it in catoks:
                if not isinstance(it, dict):
                    continue
                if it.get("connected_account_id") == ca_id and it.get("token"):
                    token = it.get("token")
                    break
            if not token:
                # fallback to first item token
                first = catoks[0]
                if isinstance(first, dict):
                    token = first.get("token") or ""

    # Headers may be returned directly; extract Authorization if present
    if not token:
        hdrs = data.get("headers") or data.get("http_headers") or data.get("httpHeaders") or {}
        if isinstance(hdrs, dict):
            auth = hdrs.get("Authorization") or hdrs.get("authorization")
            if isinstance(auth, str) and auth.startswith("Bearer "):
                token = auth.split(" ", 1)[1]

    # Choose connected_url as canonical if provided
    chosen_url = connected_url or base_url
    # Make sure chosen_url has explicit binding params
    if chosen_url:
        chosen_url = _ensure_account_bound_url(chosen_url, user_id or "singleton", ca_id)
    return {"mcp_url": chosen_url, "connected_mcp_url": connected_url, "mcp_token": token}


def _ensure_account_bound_url(url: str, user_id: str, ca_id: str) -> str:
    """Ensure the MCP URL carries explicit binding parameters for the CA/user.

    Adds/merges query params:
      - connected_account_ids=ca_id
      - user_id=user_id
    Keeps any existing params intact.
    """
    try:
        pr = urlparse(url)
        q = dict(parse_qsl(pr.query, keep_blank_values=True))
        # Merge without duplicating
        q.setdefault("connected_account_ids", ca_id)
        q.setdefault("user_id", user_id or "singleton")
        new_q = urlencode(q)
        return urlunparse((pr.scheme, pr.netloc, pr.path, pr.params, new_q, pr.fragment))
    except Exception:
        return url
