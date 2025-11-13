from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import RedirectResponse, JSONResponse, HTMLResponse
from urllib.parse import quote_plus

from mcp_agent.oauth import COMPOSIO_API_V3, OAuthManager
from mcp_agent.registry import refresh_registry_from_oauth
from computer_use_agent.tools.mcp_action_registry import sync_registered_actions

router = APIRouter()

COMPOSIO_CALLBACK = f"{COMPOSIO_API_V3}/toolkits/auth/callback"


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

    # Phase 2: hosted-link final redirect from Composio
    if ca_id:
        if status and status != "success":
            raise HTTPException(400, f"Composio reported status={status}")
        user_id = request.headers.get("X-User-Id", "singleton")
        provider = (app_name or "gmail").lower()
        try:
            OAuthManager.finalize_connected_account(provider, user_id, ca_id)
            # Ensure local cache pulls latest MCP details for this account
            try:
                OAuthManager.sync(provider, user_id, force=True)
            except Exception:
                pass
            refresh_registry_from_oauth(user_id)
            sync_registered_actions()
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
