# OAuth Refresh Required Data Contract

## Overview
This contract describes how the API responds when a run is blocked because Composio reports a non-ACTIVE connected account for a provider that is ACTIVE in our DB. The frontend should use this data to prompt the user to re-authenticate the impacted providers.

## Trigger Conditions
A run is blocked when ALL of the following are true:
- The provider has an ACTIVE connected account row in our DB for the user.
- Composio reports either:
  - `status != ACTIVE`, or
  - `auth_refresh_required == true`.

The Composio check uses the list endpoint filtered by user id:
- `GET https://backend.composio.dev/api/v3/connected_accounts?user_ids[]=<user_id>`
- If that call fails or does not include some account ids, we fall back to per-account checks in parallel.

## Provider Selection Rules
- If `tool_constraints` is provided (custom mode):
  - Start with `tool_constraints.providers`.
  - Union with providers derived from `tool_constraints.tools` by splitting `provider.tool`.
- If `tool_constraints` is not provided:
  - Use all providers that have an ACTIVE connected account for the user.

Provider keys are normalized lowercase slugs (for example: `gmail`, `slack`, `google_admin`).

## Public API Response (Pre-Queue Guard)
**Endpoint:** `POST /api/workflows/{workflow_id}/run`

**Status:** `409 Conflict`

**Body (FastAPI error envelope):**
```json
{
  "detail": {
    "error": "oauth_refresh_required",
    "providers": ["gmail", "slack"],
    "reasons": {
      "gmail": "connected_account_status=EXPIRED",
      "slack": "auth_refresh_required"
    }
  }
}
```

### Detail Fields
- `error` (string, required): constant `oauth_refresh_required`.
- `providers` (string[], required): provider slugs needing re-auth.
- `reasons` (object, optional): map of provider -> reason string.

## Internal API Response (Pre-Execute Guard)
**Endpoint:** `POST /internal/runs/{run_id}/execute`

**Status:** `409 Conflict`

**Body:** same `detail` payload as the pre-queue response.

**Side Effects:**
- `workflow_runs.status` is set to `attention`.
- `workflow_runs.metadata.oauth_refresh_required` is written for UI inspection:
```json
{
  "providers": ["gmail", "slack"],
  "reasons": {
    "gmail": "connected_account_status=EXPIRED",
    "slack": "auth_refresh_required"
  },
  "checked_at": "2025-01-10T19:42:10.123456+00:00",
  "source": "pre_execute"
}
```

## Reason Values
- `connected_account_status=<STATUS>`
- `auth_refresh_required`

`STATUS` is the Composio connected account status (examples: `INITIALIZING`, `EXPIRED`, `DISCONNECTED`, `ERROR`).

## Frontend Handling Guidance
- If `detail.error == "oauth_refresh_required"`, show OAuth re-auth prompts for the listed providers.
- Prefer the `providers` list as the source of truth; `reasons` may be absent for some providers if the check failed.
- After re-auth, re-queue the run.

## Notes
- The pre-queue guard happens before credits are debited. No run is created when the enqueue request is rejected.
- The pre-execute guard is a safety net for queued runs and records the reason in run metadata for the UI.
