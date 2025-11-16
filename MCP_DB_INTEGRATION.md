# MCP + Database Integration

This document describes how our Model Context Protocol (MCP) wiring talks to the
database, what gets persisted at each stage of the Composio OAuth flow, and
where single-tenant assumptions still exist.

---

## Architectural Overview

1. **Database layer (`framework/db`)** – SQLAlchemy models (`User`,
   `AuthConfig`, `ConnectedAccount`, `MCPConnection`) capture which human user
   connected which provider account and the HTTP endpoint + headers we must use.
   All access goes through `session_scope()` so writes take place inside a short
   transaction (`framework/db/engine.py:10-34`).
2. **OAuth + Composio adapter (`framework/mcp/oauth.py`)** – The
   `OAuthManager` orchestrates white-label OAuth with Composio, normalizes MCP
   HTTP URLs, and **persists**/refreshes them in the DB. It also exposes helper
   methods (`get_mcp_url`, `get_headers`, `sync`) that the rest of the system
   calls.
3. **Registry + actions (`framework/mcp/registry.py` and
   `framework/mcp/actions.py`)** – `init_registry()` queries the DB for any
   active provider connections, constructs `MCPClient` instances, and registers
   only the authorized tool actions on the grounding agent (`ACI`) that the
   worker can call.
4. **FastAPI routes (`framework/api/routes_mcp_auth.py`,
   `framework/api/route_composio_redirect.py`)** – API endpoints drive the
   OAuth lifecycle, kick off syncs, and refresh the registry + actions whenever
   OAuth state changes. Each route requires `X-User-Id`
   to decide which user's rows to touch.

The figure below shows the high-level flow:

```
User ↔ FastAPI (OAuth routes) ↔ OAuthManager ↔ Composio APIs
                                   ↓
                                 DB (users, connected_accounts, mcp_connections)
                                   ↓
                         MCP registry → MCP actions on ACI → Worker invocations
```

---

## Data Model

| Table | Purpose | Key fields |
| --- | --- | --- |
| `users` | Logical owner of OAuth connections. Legacy single-tenant deployments often used a single row with id `singleton`, but multi-tenant runs insert real user ids. | `id`, `created_at` (`framework/db/models.py:18-22`) |
| `auth_configs` | Stores the Composio `ac_*` ids per provider (`gmail`, `slack`, …) so we can validate that callbacks map to the intended provider. | `id`, `provider`, `name` (`framework/db/models.py:24-30`) |
| `connected_accounts` | One row per user ↔ provider connection. Unique on `(user_id, auth_config_id)` so that if a user reconnects we rewrite the existing record instead of creating duplicates. | Columns plus constraint in `framework/db/models.py:32-49` |
| `mcp_connections` | Tracks the latest HTTP endpoint + headers (JSON) for a connected account, as well as last sync timestamps and error messages. | `framework/db/models.py:51-60` |

CRUD helpers in `framework/db/crud.py` encapsulate all write patterns:

- `upsert_user`, `upsert_auth_config`, `upsert_connected_account`,
  `upsert_mcp_connection` (lines `15-112`) ensure idempotent writes during
  OAuth finalization.
- `get_active_mcp_for_provider` and `get_active_context_for_provider`
  (lines `114-164`) join `connected_accounts` with `mcp_connections` to
  return only ACTIVE accounts with a usable MCP URL.
- `disconnect_provider` / `disconnect_account` (lines `170-255`) soft-delete
  rows by nulling connection data and marking status as `DISCONNECTED`.

---

## Service-Layer Components

### OAuthManager (`framework/mcp/oauth.py`)

- **start flow**: `start_oauth` (line `72`) hits Composio’s
  `/connected_accounts` endpoint using the provider’s `auth_config_id`, returns
  the redirect URL, and tags the request with the `user_id`.
- **finalize**: `finalize_connected_account` (line `123`) waits for the
  connected account to reach `ACTIVE`, ensures an HTTP MCP URL and auth headers
  exist (generating a token if needed), then persists everything via the CRUD
  helpers before caching it in `_store`.
- **headers + registry hooks**:
  - `get_mcp_url` (line `219`) and `get_headers` (line `225`) read from the DB;
    `get_headers` will mint a fresh Authorization token if the DB lacks one and
    update `mcp_connections` so future calls stay in sync.
  - `sync` / `_sync_connection` (lines `260-418`) poll Composio to refresh the
    stored MCP URL + headers and re-upsert rows if something changed upstream.
- **Safety additions**: `_ensure_mcp_server` and `_generate_mcp_url`
  (lines `476-595`) guarantee we always get an account-bound HTTP endpoint with
  `connected_account_ids` & `user_id` query params, and always attach
  `X-Connected-Account-Id` in headers for downstream auditing.

### MCP registry (`framework/mcp/registry.py`)

- `init_registry` (lines `10-33`) rebuilds the in-memory `MCP` dict by reading
  all ACTIVE MCP URLs from the DB and constructing `MCPClient` objects using
  the provider-specific headers returned by `OAuthManager.get_headers`.
- If no DB entry exists (e.g., fresh dev environment) it optionally falls back
  to environment-provided URLs/tokens.
- `refresh_registry_from_oauth` (line `40`) is a thin wrapper the routes call
  after syncing OAuth so that new MCP clients become available immediately.

### MCP actions (`mcp_agent/actions.py`)

- Each action (e.g., `slack_post_message`, `gmail_send_email`) first checks
  `OAuthManager.is_authorized` before grabbing the corresponding registry client
  and calling `client.call`. This prevents the worker from attempting MCP
  tools when DB state says the user is disconnected (`framework/mcp/actions.py:14-196`).
- `configure_mcp_action_filters` limits the provider/tool set, while
  `computer_use_agent/tools/mcp_action_registry.py:sync_registered_actions`
  rebinds the grounding agent (`ACI`) so only currently authorized MCP tools
  are exposed to the worker prompt.

### FastAPI surface (`framework/api/routes_mcp_auth.py`)

- `/api/mcp/auth/{provider}/start` → `OAuthManager.start_oauth`.
- `/api/mcp/auth/{provider}/callback` or `/api/composio-redirect` →
  finalizes, syncs, refreshes registry/actions.
- `/api/mcp/auth/{provider}` `DELETE` → marks DB rows as disconnected and
  clears the registry.
- `/api/mcp/auth/status` → re-syncs each provider (best effort) then reports
  `OAuthManager.is_authorized` per provider.

Every route requires an explicit `X-User-Id` header so in theory
different tenants can co-exist once the rest of the stack forwards that header.

---

## OAuth → MCP Lifecycle

1. **Start OAuth**
   - Client hits `/api/mcp/auth/{provider}/start`.
   - Route reads `X-User-Id`, builds the redirect via
     `build_redirect`, and returns the Composio-hosted URL (`routes_mcp_auth.py:23-39`).
2. **Provider redirects back**
   - Our branded redirect endpoint `/api/composio-redirect` either forwards the
     initial `code/state` back to Composio or accepts the final
     `connectedAccountId` callback (`route_composio_redirect.py:13-56`).
3. **Finalize + persist**
   - `OAuthManager.finalize_connected_account` upserts the DB rows, generates
     the MCP URL/token as needed, and caches the result.
   - `OAuthManager.sync(..., force=True)` immediately refreshes the DB with the
     latest headers + URLs from Composio.
4. **Refresh registry / actions**
   - `refresh_registry_from_oauth` rebuilds the in-memory `MCP` client map,
     then `sync_registered_actions` rebinds the worker-facing methods so only
     the newly authorized tools appear in prompts.
5. **Runtime usage**
   - When the worker attempts, say, `gmail_send_email`, it first confirms DB
     authorization via `OAuthManager.is_authorized`, then reuses the cached
     `MCPClient` to call the MCP server over HTTP (`actions.py:90-199`).
6. **Disconnect / resync**
   - `/api/mcp/auth/{provider}` `DELETE` or `OAuthManager.disconnect` updates
     the DB, clears cached headers/URLs, and re-registers the (now reduced)
     action set (`routes_mcp_auth.py:96-118`).

Because the registry is always rebuilt from the DB, we stay resilient across
process restarts: `app_lifespan` in `framework/api/server.py:27-66` automatically
invokes `OAuthManager.sync` and `refresh_registry_from_oauth` for the
the user defined by `TB_USER_ID` when FastAPI boots.

---

## Tenancy Model

### Current state (single-tenant)

- The API **requires** `user_id` everywhere (`routes_mcp_auth.py:25`,
  `route_composio_redirect.py:29`, `mcp/registry.py:12`, etc.).
- The orchestrator server warm-up only syncs when `TB_USER_ID` is set
  (`framework/api/server.py:27-66`).
- `OAuthManager` keeps an in-memory `_store` keyed by user id, but every call
  expects a non-empty string (`framework/mcp/oauth.py:78-226`).
- Result: unless a caller explicitly supplies `X-User-Id`, all OAuth state,
  DB rows, and registry entries belong to the single shared tenant.

### Multi-tenant readiness

The schema and CRUD logic already separate rows by `user_id`, and every public
entry point accepts a `user_id`. To graduate to true multi-tenancy we would need
to:

1. **Forward real user ids** from the UI / orchestrator to every MCP route (via
   `X-User-Id` header) and to any internal calls to `OAuthManager.*`.
2. **Rebuild registries per user**. Today `MCP` is a single global dict. For
   multi-tenant operation we would likely maintain `{user_id: {provider:
   MCPClient}}` or instantiate registry/ACI per request context so providers
   cannot bleed across tenants.
3. **Inject user context into worker runs** so that `OAuthManager.is_authorized`
   and action calls look up the correct user’s DB rows instead of a legacy singleton user id.
4. **Audit caches** (`OAuthManager._store`, ACI method bindings, etc.) so they
   become user-scoped or stateless.

Until those steps are finished, **the system is effectively single-tenant** with
multi-tenant support partially scaffolded at the API boundary and in the DB.

---

## Operational Notes

- **Environment variables**: `DB_URL`, `DB_ECHO` (database); `COMPOSIO_API_KEY`,
  `COMPOSIO_*_AUTH_CONFIG_ID`, `COMPOSIO_REDIRECT`, `COMPOSIO_TOKEN`,
  `COMPOSIO_MCP_SERVER_ID` manage MCP/OAuth behavior.
- **Warm start**: restarting the API automatically (best-effort) re-syncs
  Composio state for the specified user so previously connected providers keep
  working without manual intervention (`framework/api/server.py:27-66`).
- **Debug aids**: `/api/mcp/auth/_debug/*` routes expose redirect URLs,
  Config status, direct MCP test calls, and raw DB counts for fast triage.
- **Local testing**: `tests/*` scripts use the specified user id and hit the
  same API routes, making it easy to reproduce authorization flows without a UI.

---

This document should give anyone touching MCP integrations enough context to
trace how provider OAuth state flows into the database and back out into the
worker runtime, and to understand why the current deployment behaves as a
single-tenant system. Refer to the linked modules for implementation details
when making changes. 
