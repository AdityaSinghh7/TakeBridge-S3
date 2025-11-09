# Frontend ↔︎ MCP/OAuth Contract

This document describes the HTTP contracts our frontend uses to drive MCP OAuth
and orchestrator runs. We are dev-only right now, so every endpoint hangs off
the FastAPI server root you're running locally (default `http://localhost:8000`,
or whatever tunnel/exposed host you point Composio at). Unless noted otherwise:

> Dev-only scope
> - start the FastAPI server locally with `uvicorn framework.api.server:app --reload --port 8000` (or equivalent) before hitting these routes;
> - keep Composio configured to call back into the same host (see `framework/settings.py:7`, where `OAUTH_REDIRECT_BASE` defaults to `http://localhost:8000`);
> - frontend builds should pass their own dev redirect URLs (e.g., `http://localhost:3000/settings/integrations`) through the `redirect_*` fields documented below so the server can bounce users back into your UI.

- include `X-User-Id` with the logical tenant id (defaults to `singleton`);
- requests and responses are JSON (`application/json`);
- HTTP errors are returned as `{"detail": "<message>"}` with the status code that
  best represents the failure.

---

## Endpoint catalog

| Purpose | Method & Path |
| --- | --- |
| List providers and auth state | `GET /api/mcp/auth/providers` |
| Describe available tools per provider | `GET /api/mcp/auth/tools/available` |
| Kick off OAuth | `GET /api/mcp/auth/{provider}/start` |
| Composio redirect passthrough | `GET /api/composio-redirect` |
| Legacy callback (optional) | `GET /api/mcp/auth/{provider}/callback` |
| Manual finalize (connectedAccountId known) | `POST /api/mcp/auth/{provider}/finalize` |
| Live poll for OAuth state | `GET /api/mcp/auth/{provider}/status/live` |
| Cached auth status snapshot | `GET /api/mcp/auth/status` |
| Disconnect provider | `DELETE /api/mcp/auth/{provider}` |
| Stream runner with full payload | `POST /orchestrate/stream` |
| Stream runner (compat task-only) | `GET /orchestrate/stream?task=...` |
| Fire-and-forget run (no streaming) | `POST /orchestrate` |

---

## OAuth endpoints

### `GET /api/mcp/auth/providers`

Returns every provider the backend knows about plus caller-specific flags.

```
Response 200
{
  "providers": [
    {
      "provider": "gmail",
      "display_name": "Gmail",
      "authorized": true,
      "auth_config_present": true,
      "actions": ["gmail_send_email", "gmail_search"]
    },
    ...
  ]
}
```

### `GET /api/mcp/auth/tools/available`

Query params: `provider` (optional slug). Returns docstrings and availability for
each MCP action. Use this to populate tool pickers.

```
Response 200
{
  "providers": [
    {
      "provider": "slack",
      "authorized": false,
      "actions": [
        {"name": "slack_post_message", "doc": "..."},
        {"name": "slack_search_messages", "doc": "..."}
      ]
    }
  ]
}
```

### `GET /api/mcp/auth/{provider}/start`

Starts the Composio OAuth flow.

Query params:

| Name | Type | Notes |
| --- | --- | --- |
| `redirect_success` | string? | (optional) absolute URL to redirect the browser to after OAuth succeeds. |
| `redirect_error` | string? | (optional) absolute URL to redirect on failure (the backend appends `?error=...`). |

Response:

```
200 { "authorization_url": "https://backend.composio.dev/oauth?..." }
```

The frontend should open the returned URL in a popup/tab. When Composio is done
it will redirect the browser to **our** `/api/composio-redirect` handler; that
handler will in turn look up the caller-provided redirect hints and forward the
browser there (or default to `/settings/integrations`). No additional form data
is required—just set the query params when starting OAuth.

### `GET /api/composio-redirect`

White-label passthrough with two phases:

1. Provider → TakeBridge: forwards the initial `code/state` to Composio.
2. Composio → TakeBridge: receives `connectedAccountId`, finalizes, refreshes
   registry, and finally issues a `302` to the `redirect_success` URL given at
   start (or `/settings/integrations`). On failure it falls back to
   `redirect_error` (if provided) with `?error=...`.

### `GET /api/mcp/auth/{provider}/callback`

Legacy callback for providers that still call this route directly. Behavior
matches `/api/composio-redirect`: we sync, refresh registries, then redirect to
the supplied `redirect_success` (if any) or `/settings/integrations`.

### `POST /api/mcp/auth/{provider}/finalize`

Used when the frontend already knows the `connectedAccountId` (e.g., Composio
hosted link). Body:

```
{
  "connected_account_id": "ca_...",
  "redirect_success": "http://localhost:3000/integrations/callback (optional)",
  "redirect_error": "http://localhost:3000/integrations/callback (optional)"
}
```

The backend finalizes, syncs, refreshes actions, and returns the summary JSON.

### `GET /api/mcp/auth/{provider}/status/live`

For polling UI. Forces a Composio sync (`force=True`) before responding.

```
Response 200
{
  "provider": "gmail",
  "authorized": true,
  "connected_account_id": "ca_123",
  "auth_config_id": "ac_456",
  "mcp_url": "https://...",
  "has_auth_headers": true
}
```

### `GET /api/mcp/auth/status`

Lightweight cached status (best-effort sync using last known data). Response is
a `{provider: bool}` map.

### `DELETE /api/mcp/auth/{provider}`

Disconnects either every connection for the user/provider or a specific
connected account when `?connected_account_id=ca_123` is provided. Response:

```
{"status":"disconnected","provider":"gmail","updated_accounts":1,"cleared_connections":1}
```

---

## Tool selection for streaming runs

The SSE endpoint now accepts JSON via `POST /orchestrate/stream`. Payload shape:

```
{
  "task": "Pay the outstanding invoice and DM finance",
  "worker": {... overrides ...},
  "grounding": {... overrides ...},
  "controller": {... overrides ...},
  "tool_constraints": {
    "mode": "auto" | "custom",
    "providers": ["gmail","slack"],
    "tools": ["gmail_send_email","slack_post_message"]
  }
}
```

- `mode: "auto"` (default) exposes every authorized provider for the user.
- `mode: "custom"` restricts MCP actions to the chosen providers/tools.
  Providers are lower-cased slugs; tool names match the action names returned by
  `/api/mcp/auth/tools/available`.
- `providers` and `tools` are optional; you can filter by provider only (all
  actions for those providers) or by explicit action names.

The server emits an `runner.tools.configured` event (via telemetry) and trims
the MCP action bindings before the worker prompt is built, ensuring the LLM
only sees the allowed tools. After each run the filter resets to `auto`.

### SSE response format

POST `/orchestrate/stream` responds with `text/event-stream`. Important events:

| Event | Payload |
| --- | --- |
| `response.created` | `{ "status": "accepted" }` |
| `response.in_progress` | `{ "status": "running" }` |
| `runner.started`, `runner.step.*` | Telemetry for UI streaming (unchanged) |
| `server.keepalive` | Sent every 15s to keep connections open |
| `response` | Final `RunnerResult` dataclass serialized to JSON |
| `response.completed` | `{ "status": "...", "completion_reason": "..." }` |
| `response.failed` / `error` | Error payload if orchestration crashes |

The legacy `GET /orchestrate/stream?task=...` endpoint remains for backward
compatibility but cannot accept tool constraints; new integrations should use
the POST variant.

### `POST /orchestrate`

Non-streaming alternative: submit the same payload schema, receive the complete
`RunnerResult` once execution finishes (no SSE).

---

## Status polling cadence

A typical frontend flow:

1. Call `GET /api/mcp/auth/providers` to render available integrations.
2. When user clicks “Connect Slack”, call
   `GET /api/mcp/auth/slack/start?redirect_success=http://localhost:3000/dev/callback&redirect_error=http://localhost:3000/dev/callback`.
3. Open the returned Composio URL in a popup. After completion,
   `/api/composio-redirect` will redirect the browser back to the provided URL
   (with `?error=` on failures).
4. Poll `GET /api/mcp/auth/slack/status/live` until `authorized=true`.
5. Use `GET /api/mcp/auth/tools/available?provider=slack` to show which actions
   are available.
6. When starting an orchestrated run, pass the desired subset of providers/tools
   in `tool_constraints` within the `POST /orchestrate/stream` payload.
7. Let the user disconnect via `DELETE /api/mcp/auth/{provider}` when necessary.

This contract keeps the frontend in control of navigation and tool curation
while ensuring backend state is always sourced from the latest Composio data.
