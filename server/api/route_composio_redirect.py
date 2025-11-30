from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import RedirectResponse, JSONResponse, HTMLResponse
from urllib.parse import quote_plus
import os

from mcp_agent.core.context import AgentContext
from mcp_agent.registry.oauth import COMPOSIO_API_V3, OAuthManager
from mcp_agent.user_identity import normalize_user_id
from mcp_agent.action_registry import sync_registered_actions
from computer_use_agent.grounding.grounding_agent import ACI
from jose import jwt, JWTError
from vm_manager.config import settings

router = APIRouter()

COMPOSIO_CALLBACK = f"{COMPOSIO_API_V3}/toolkits/auth/callback"


def _extract_user_from_jwt(request: Request) -> str | None:
    """
    Extract user_id from JWT token in Authorization header.
    Returns None if no valid token is present (allows fallback to other methods).
    """
    auth_header = request.headers.get("Authorization", "").strip()
    if not auth_header.startswith("Bearer "):
        return None
    
    try:
        token = auth_header.split(" ", 1)[1]
        payload = jwt.decode(
            token,
            settings.SUPABASE_JWT_SECRET,
            algorithms=[settings.SUPABASE_JWT_ALG],
            options={
                "verify_signature": True,
                "verify_exp": True,
                "verify_iat": True,
                "verify_aud": False,
            },
        )
        sub = payload.get("sub") or payload.get("user_id")
        if sub:
            return normalize_user_id(sub)
    except (JWTError, Exception):
        # If JWT validation fails, return None to allow fallback
        pass
    return None


def _require_user_id(request: Request) -> str:
    """
    Get user_id from JWT token (preferred) or fall back to X-User-Id header/query param.
    
    This supports both:
    1. JWT-based auth (from Supabase) - preferred for authenticated requests
    2. X-User-Id header (for backward compatibility)
    3. Query parameter (for OAuth callbacks from external providers - user_id embedded in redirect URL)
    4. dev-local fallback (only for local development - should be removed in production)
    
    OAuth callbacks from external providers (like Composio) can't include JWT tokens,
    so they use user_id in query parameters (embedded in redirect URL by _redirect_with_user).
    """
    # Try JWT auth first (if available and provided)
    user_id = _extract_user_from_jwt(request)
    if user_id:
        return user_id
    
    # Fallback to legacy methods (for OAuth callbacks)
    raw = (request.headers.get("X-User-Id") or "").strip()
    if not raw:
        raw = (request.query_params.get("user_id") or "").strip()
    if not raw:
        # Only use dev-local as last resort for local development
        # TODO: Remove this fallback in production - require proper auth
        raw = os.getenv("TB_DEFAULT_USER_ID", "").strip()
    if not raw:
        raise HTTPException(
            400,
            "Missing authentication. Provide either: "
            "1) JWT token in Authorization header, or "
            "2) X-User-Id header/user_id query parameter (for OAuth callbacks)"
        )
    try:
        return normalize_user_id(raw)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


def _attach_error(url: str | None, message: str) -> str | None:
    if not url:
        return None
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}error={quote_plus(message[:400])}"


@router.get("/api/composio-redirect")
def composio_redirect(request: Request):
    """Handle both phases of white-label flow:

    1) Provider -> your redirect with code/state: forward to Composio's callback.
    2) Composio -> your redirect with connectedAccountId: finalize locally and refresh registry.
    """
    qp = request.query_params
    ca_id = qp.get("connectedAccountId")
    status = qp.get("status")
    app_name = (qp.get("appName") or qp.get("provider") or "").lower()
    state = qp.get("state")  # OAuth state parameter (preserved through flow)

    # Phase 2: hosted-link final redirect from Composio
    if ca_id:
        if status and status != "success":
            raise HTTPException(400, f"Composio reported status={status}")
        
        # Try to get user_id from stored OAuth state first
        user_id = None
        if state:
            user_id = OAuthManager.get_oauth_user_id(state)
        
        # Fallback 1: Try other methods (JWT, X-User-Id, query param)
        if not user_id:
            try:
                user_id = _require_user_id(request)
            except HTTPException:
                pass
        
        # Fallback 2: Try to get user_id from database if connected_account already exists
        if not user_id and ca_id:
            try:
                from mcp_agent.registry.db_models import ConnectedAccount
                from shared.db.engine import session_scope
                with session_scope() as db:
                    account = db.get(ConnectedAccount, ca_id)
                    if account:
                        user_id = account.user_id
            except Exception:
                pass
        
        # Fallback 3: Try to get user_id from Composio API
        # When we created the connected account, we passed user_id in the connection object
        # Composio should return it when we query the account
        if not user_id and ca_id:
            try:
                from mcp_agent.registry.oauth import _get_connected_account
                account_details = _get_connected_account(ca_id)
                # Composio returns user_id in connection.user_id (the one we passed when creating)
                connection = account_details.get("connection") or {}
                composio_user_id = (
                    connection.get("user_id")
                    or account_details.get("user_id")
                    or (account_details.get("user") or {}).get("id")
                )
                if composio_user_id:
                    # This should be the user_id we passed when creating the account
                    user_id = normalize_user_id(composio_user_id)
            except Exception:
                pass
        
        # If we still don't have user_id, we can't proceed
        if not user_id:
            provider = (app_name or "gmail").lower()
            raise HTTPException(
                400,
                "Missing authentication. Could not determine user_id from OAuth callback. "
                "Please ensure you're using a valid OAuth flow or restart the connection."
            )
        
        provider = (app_name or "gmail").lower()
        context = AgentContext.create(user_id=user_id)
        try:
            OAuthManager.finalize_connected_account(context, provider, ca_id)
            # Registry is DB-backed, no manual refresh needed
            sync_registered_actions(user_id, aci_class=ACI)
        except Exception as e:
            # Attempt to surface upstream error body if available (requests HTTPError)
            detail = str(e)
            resp = getattr(e, "response", None)
            if resp is not None:
                try:
                    detail = f"{detail} | upstream: {resp.text[:500]}"
                except Exception:
                    pass
            error_redirect = OAuthManager.consume_redirect_hint(provider, user_id, success=False)
            if error_redirect:
                target = _attach_error(error_redirect, detail)
                if target:
                    return RedirectResponse(url=target, status_code=302)
            raise HTTPException(400, f"Finalize failed: {detail}")
        # Bounce to UI success page
        success_redirect = OAuthManager.consume_redirect_hint(provider, user_id, success=True)
        target = success_redirect or f"/settings/integrations?connected={provider}"
        return RedirectResponse(url=target, status_code=302)

    # Phase 1: provider -> your redirect: forward to Composio callback
    # Extract state parameter and store user_id for Phase 2
    state = qp.get("state")
    if state:
        # Try to get user_id from request (JWT, header, query param)
        # This will be used in Phase 2 when Composio redirects back
        try:
            user_id = _require_user_id(request)
            if user_id:
                OAuthManager.store_oauth_user_id(state, user_id)
        except HTTPException:
            # If we can't get user_id here, try to get it from stored state
            stored_user_id = OAuthManager.get_oauth_user_id(state)
            if stored_user_id:
                # Keep it stored for Phase 2
                OAuthManager.store_oauth_user_id(state, stored_user_id)
    
    qs = request.url.query
    url = COMPOSIO_CALLBACK if not qs else f"{COMPOSIO_CALLBACK}?{qs}"
    return RedirectResponse(url=url, status_code=302)


@router.get("/settings/integrations")
def integrations_landing(connected: str | None = None):
    """Minimal landing page for post-OAuth redirect.

    Returns a simple confirmation so local testing doesn't 404 when redirected
    to `/settings/integrations?connected=...`.
    """
    msg = "finalization done"
    if connected:
        msg = f"finalization done for {connected}"
    # lightweight HTML for browser flows, still usable via curl
    html = f"""
    <html>
      <head><title>Integrations</title></head>
      <body>
        <h3>{msg}</h3>
      </body>
    </html>
    """
    return HTMLResponse(content=html, status_code=200)
