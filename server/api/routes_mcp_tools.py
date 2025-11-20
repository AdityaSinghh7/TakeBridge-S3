"""
TEST-ONLY ROUTES

These endpoints exist solely to help you live-test MCP connectivity
without needing to drive the Worker/LLM. Do NOT expose in production.
"""

from fastapi import APIRouter, Request, HTTPException

from mcp_agent.registry.oauth import OAuthManager
from mcp_agent.registry.manager import RegistryManager
from mcp_agent.core.context import AgentContext
from mcp_agent.user_identity import normalize_user_id
from computer_use_agent.tools.mcp_action_registry import sync_registered_actions


router = APIRouter(prefix="/api/mcp/tools", tags=["mcp-tools (test-only)"])


def _require_user_id(request: Request) -> str:
    raw = (request.headers.get("X-User-Id") or "").strip()
    if not raw:
        raise HTTPException(400, "Missing X-User-Id header.")
    try:
        return normalize_user_id(raw)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@router.post("/gmail/send_email")
def gmail_send_email_route(payload: dict, request: Request):
    """Send an email using the Gmail MCP tool.

    Body fields:
    - to (str, required)
    - subject (str, required)
    - body (str, required)
    - cc (str, optional)
    - bcc (str, optional)
    - thread_id (str, optional)
    """
    user_id = _require_user_id(request)
    context = AgentContext.create(user_id)
    
    if not OAuthManager.is_authorized(context, "gmail"):
        raise HTTPException(400, "unauthorized: gmail not connected for this user")

    # Ensure MCP URL/headers are present
    try:
        OAuthManager.sync("gmail", user_id, force=True)
    except Exception:
        # best-effort; continue even if sync hiccups
        pass

    # Registry is DB-backed, no manual refresh needed
    sync_registered_actions(user_id)
    
    registry = RegistryManager(context)
    client = registry.get_mcp_client("gmail")
    if not client:
        raise HTTPException(400, "unconfigured: gmail MCP client missing")

    # Normalize recipients: accept string or list, output list[str]
    def _norm_recipients(x):
        if x is None or x == "":
            return []
        if isinstance(x, list):
            return [s.strip() for s in x if isinstance(s, str) and s.strip()]
        if isinstance(x, str):
            parts = [p.strip() for p in x.replace(";", ",").split(",")]
            return [p for p in parts if p]
        return []

    def _primary_plus_rest(x):
        lst = _norm_recipients(x)
        if not lst:
            return "", []
        return lst[0], lst[1:]

    primary_in = payload.get("to") or payload.get("recipient_email")
    primary, extra_tos = _primary_plus_rest(primary_in)
    cc = _norm_recipients(payload.get("cc"))
    bcc = _norm_recipients(payload.get("bcc"))
    # Preserve intent: spill any additional 'to' into CC
    cc = cc + extra_tos

    args = {
        # Composio expects primary recipient as a single string
        "recipient_email": primary,
        "subject": payload.get("subject", ""),
        "body": payload.get("body", ""),
        "cc": cc,
        "bcc": bcc,
    }
    if payload.get("thread_id"):
        args["thread_id"] = payload["thread_id"]
    # Optional: allow HTML bodies
    if isinstance(payload.get("is_html"), bool):
        args["is_html"] = payload["is_html"]

    # Composio Gmail tool name is uppercase with provider prefix
    return client.call("GMAIL_SEND_EMAIL", args)
