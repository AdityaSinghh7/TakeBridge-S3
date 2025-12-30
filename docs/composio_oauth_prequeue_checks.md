# Composio OAuth Pre-Queue Status Checks

## Goal
Block runs when a provider is ACTIVE in the DB but Composio reports a non-ACTIVE or refresh-required state. Return the list of impacted providers so the frontend can trigger OAuth reauth.

## Current State
- Connected accounts are stored in `connected_accounts` via `mcp_agent/registry/db_models.py`.
- `OAuthManager.auth_status()` calls Composio `GET /api/v3/connected_accounts/{id}` and flags `refresh_required`, but it does not persist expiry state.
- Queueing happens in `POST /workflows/{workflow_id}/run` (`server/api/routes_workflows.py`).
- Execution starts in `POST /internal/runs/{run_id}/execute` (`server/api/server.py`).
- `/mcp/auth/providers` already batch-checks refresh status using `_get_connected_account` in parallel.

## Proposed Flow
1. **Pre-queue guard (primary)**
   - Add a status check in `enqueue_workflow_run` before debiting credits and inserting the run row.
   - If any provider has changed status, reject the request and return a special error payload.
2. **Pre-execute guard (safety net)**
   - Re-run the same status check in `internal_execute_run` before orchestration starts.
   - If failing, update the run status (e.g., `attention`) and include provider details in run metadata.

## Provider Selection Rules
- If `tool_constraints` is provided (custom mode):
  - Start with `tool_constraints.providers` if present.
  - If `tool_constraints.tools` is present, derive providers from `provider.tool` prefixes and union them in.
- If `tool_constraints` is not provided:
  - Check **all** providers for the user that are `connected_accounts.status == ACTIVE`.
- Only check providers with ACTIVE rows in the DB to avoid unnecessary Composio calls.

## Status Check Logic
- Prefer the list endpoint so the user’s connected accounts are fetched in one call:
  - `GET https://backend.composio.dev/api/v3/connected_accounts?user_ids[]=<user_id>&statuses[]=ACTIVE`
- Filter the list response to only the providers we care about (toolkit slug), then map back to DB provider names.
- Treat either of these as a changed status:
  - `status != ACTIVE`
  - `auth_refresh_required == true`
- Capture a per-provider reason:
  - `connected_account_status=<STATUS>` or `auth_refresh_required`
- If the list endpoint fails, fall back to per-account checks in parallel (thread pool) to avoid blocking.
- Ensure the check path bypasses cached `auth_status` so queue checks are always fresh.

## Error Contract
- Pre-queue response (recommended): HTTP 409 or 412 with a structured detail:
  - `{"error": "oauth_refresh_required", "providers": ["gmail", "slack"], "reasons": {"gmail": "connected_account_status=EXPIRED"}}`
- Pre-execute response:
  - Update run status (e.g., `attention`) and store the same fields in `workflow_runs.metadata` for UI display.

## Implementation Notes
- Add a shared module (e.g., `mcp_agent/registry/connected_accounts.py`) that:
  - Lists ACTIVE connected accounts from the DB for a user, optionally filtered by provider.
  - Fetches Composio status via the list endpoint using `user_ids` filter.
  - Normalizes Composio list payloads into a `{provider: status_info}` map.
  - Provides a single `check_provider_status(user_id, providers)` helper used by both pre-queue and pre-execute.
- Persist `tool_constraints` into run metadata at enqueue so the pre-execute guard can reuse the same provider scope.
- Keep all remote calls parallelized (thread pool) for any per-account fallback.
- Ensure the pre-queue check happens before credit debit in `enqueue_workflow_run`.
- Log structured events with `user_id`, `workflow_id`, and `blocked_providers` for easier tracing.
- Confirm how `tool_constraints` will be passed to the queue endpoint (payload vs. workflow plan metadata) and document the chosen source.
