from .registry import MCP, init_registry, is_registered
from .oauth import OAuthManager
from framework.utils.streaming import emit_event
from framework.grounding.grounding_agent import ACI
init_registry()

def _sleep_snippet(sec: float = 0.5) -> str:
    return f"import time; time.sleep({sec})"

def mcp_action(func):
    func.is_mcp_action = True
    return func

@mcp_action
def slack_post_message(self, channel: str, text: str):
    """Send a message to a channel.
    Args:
        channel: Channel handle (e.g., '#ops') or channel ID.
        text: Message body to send.
    Returns:
        A short pyautogui-compatible snippet (sleep) to keep the single-action contract.
    Side Effects:
        - Sends a message using the configured connection.
        - Emits telemetry events for observability.
        - Appends 'SLACK_POST_RESULT=...' to agent notes for planning.
    Error Handling:
        If the connection is unavailable, emits a 'skipped' event,
        records nothing, and returns a short sleep snippet.
    """
    # Authorization and registration checks
    if getattr(self, "_validation_only", False):
        return _sleep_snippet(0.0)
    if not OAuthManager.is_authorized("slack"):
        emit_event("mcp.call.skipped", {"server":"slack","reason":"unauthorized"})
        return _sleep_snippet(0.2)
    client = MCP.get("slack")
    if not client or not is_registered("slack"):
        emit_event("mcp.call.skipped", {"server":"slack","reason":"unconfigured"})
        return _sleep_snippet(0.2)
    res = client.call("post_message", {"channel": channel, "text": text})
    emit_event("mcp.call.completed", {"server":"slack","tool":"post_message","response":res})
    # Optionally save result into the agent notes for follow-up
    self.notes.append(f"SLACK_POST_RESULT={res}")
    return _sleep_snippet(0.2)

@mcp_action
def slack_search_messages(self, query: str, max_results: int = 10):
    """Search messages and save top hits.
    Args:
        query: Search query supported by the service.
        max_results: Max number of results to fetch.
    Returns:
        A short pyautogui-compatible snippet (sleep) to keep the single-action contract.
    Side Effects:
        - Performs a message search over the configured connection.
        - Emits telemetry events for observability.
        - Appends 'SLACK_SEARCH=...' to agent notes (use in next-step planning).
    Error Handling:
        If the connection is unavailable, emits a 'skipped' event and returns a sleep snippet.
    """
    if getattr(self, "_validation_only", False):
        return _sleep_snippet(0.0)
    if not OAuthManager.is_authorized("slack"):
        emit_event("mcp.call.skipped", {"server":"slack","reason":"unauthorized"})
        return _sleep_snippet(0.2)
    client = MCP.get("slack")
    if not client or not is_registered("slack"):
        emit_event("mcp.call.skipped", {"server":"slack","reason":"unconfigured"})
        return _sleep_snippet(0.2)
    res = client.call("search_messages", {"query": query, "limit": max_results})
    self.notes.append(f"SLACK_SEARCH={res}")
    emit_event("mcp.call.completed", {"server":"slack","tool":"search_messages","response":res})
    return _sleep_snippet(0.2)

def _norm_recipients(x):
    if x is None or x == "":
        return []
    if isinstance(x, list):
        return [s.strip() for s in x if isinstance(s, str) and s.strip()]
    if isinstance(x, str):
        return [p.strip() for p in x.replace(";", ",").split(",") if p.strip()]
    return []

def _primary_plus_rest(x):
    lst = _norm_recipients(x)
    if not lst:
        return "", []
    return lst[0], lst[1:]

@mcp_action
def gmail_send_email(self, to: str, subject: str, body: str, cc: str = "", bcc: str = "", thread_id: str = "", is_html: bool = False):
    """Send an email.
    Args:
        to: Comma-separated recipients.
        subject: Subject line text.
        body: Plain text or simple HTML body.
        cc: Optional comma-separated CC recipients.
        bcc: Optional comma-separated BCC recipients.
        thread_id: Optional Gmail thread to reply into.
    Description:
        Sends an email via Gmail API using the authenticated user's Google profile display name. At least one of recipient_email, cc, or bcc must be provided. Atleast one of subject or body must be provided. Requires `is_html=True` if the body contains HTML and valid `s3key`, `mimetype`, `name` for any attachment.

    Returns:
        data: object
        error: string
        successful: boolean
    """
    if getattr(self, "_validation_only", False):
        return _sleep_snippet(0.0)
    if not OAuthManager.is_authorized("gmail"):
        emit_event("mcp.call.skipped", {"server":"gmail","reason":"unauthorized"})
        return _sleep_snippet(0.2)
    client = MCP.get("gmail")
    if not client or not is_registered("gmail"):
        emit_event("mcp.call.skipped", {"server":"gmail","reason":"unconfigured"})
        return _sleep_snippet(0.2)
    primary, extra_tos = _primary_plus_rest(to)
    cc_list = _norm_recipients(cc) + extra_tos
    bcc_list = _norm_recipients(bcc)

    args = {
        # Composio expects 'recipient_email' as a single string
        "recipient_email": primary,
        "subject": subject,
        "body": body,
        "cc": cc_list,
        "bcc": bcc_list,
        "is_html": bool(is_html),
    }
    if thread_id:
        args["thread_id"] = thread_id
    # Composio tool name is provider-prefixed
    res = client.call("GMAIL_SEND_EMAIL", args)
    self.notes.append(f"GMAIL_SEND_RESULT={res}")
    emit_event("mcp.call.completed", {"server":"gmail","tool":"send_email","response":res})
    return _sleep_snippet(0.2)

@mcp_action
def gmail_search(self, query: str, max_results: int = 20):
    """Search mail and save top message ids/subjects.
    Args:
        query: Search query (e.g., 'from:alice has:attachment').
        max_results: Max number of results to fetch.
    Returns:
        A short pyautogui-compatible snippet (sleep) to keep the single-action contract.
    Side Effects:
        - Performs a message search using the configured connection.
        - Emits telemetry events for observability.
        - Appends 'GMAIL_SEARCH=...' to agent notes for planning.
    Error Handling:
        If the connection is unavailable, emits a 'skipped' event and returns a sleep snippet.
    """
    if getattr(self, "_validation_only", False):
        return _sleep_snippet(0.0)
    if not OAuthManager.is_authorized("gmail"):
        emit_event("mcp.call.skipped", {"server":"gmail","reason":"unauthorized"})
        return _sleep_snippet(0.2)
    client = MCP.get("gmail")
    if not client or not is_registered("gmail"):
        emit_event("mcp.call.skipped", {"server":"gmail","reason":"unconfigured"})
        return _sleep_snippet(0.2)
    # Map to a supported Gmail tool (fetch emails with query)
    res = client.call("GMAIL_FETCH_EMAILS", {"query": query, "limit": max_results})
    self.notes.append(f"GMAIL_SEARCH={res}")
    emit_event("mcp.call.completed", {"server":"gmail","tool":"search_messages","response":res})
    return _sleep_snippet(0.2)

# Register these MCP actions onto the base ACI so Worker can discover
# them when it introspects the grounding agent class/type.
def _provider_actions_map():
    return {
        "slack": (slack_post_message, slack_search_messages),
        "gmail": (gmail_send_email, gmail_search),
    }


def _reset_mcp_actions_on_aci() -> None:
    """Remove all MCP action methods from ACI so we can rebuild accurately."""
    provider_actions = _provider_actions_map()
    for fns in provider_actions.values():
        for fn in fns:
            if hasattr(ACI, fn.__name__):
                try:
                    delattr(ACI, fn.__name__)
                except Exception:
                    pass


def _register_mcp_actions_on_aci() -> None:
    """Register MCP actions only for providers that are OAuth-authorized and registered.

    This prevents unavailable actions from being interpolated into the worker
    system prompt before the user connects providers via OAuth.
    """
    provider_actions = _provider_actions_map()
    for provider, fns in provider_actions.items():
        if not OAuthManager.is_authorized(provider):
            emit_event(
                "mcp.actions.registration.skipped",
                {"server": provider, "reason": "unauthorized"},
            )
            continue
        if not is_registered(provider):
            emit_event(
                "mcp.actions.registration.skipped",
                {"server": provider, "reason": "unconfigured"},
            )
            continue
        for fn in fns:
            setattr(ACI, fn.__name__, fn)
        emit_event(
            "mcp.actions.registration.completed",
            {"server": provider, "actions": [fn.__name__ for fn in fns]},
        )

def register_mcp_actions() -> None:
    """Public, idempotent registration entry point.

    Call this after completing OAuth to expose newly available MCP actions
    to the Worker prompt. Safe to call multiple times.
    """
    _reset_mcp_actions_on_aci()
    _register_mcp_actions_on_aci()

_register_mcp_actions_on_aci()
