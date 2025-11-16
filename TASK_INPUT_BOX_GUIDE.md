# Task Input Box → `/orchestrate/stream` Integration

This guide explains how the frontend should power the “main task” input box by
calling the streaming orchestrator endpoint implemented in
`framework/api/server.py`. The deprecated `/orchestrate/runs` endpoint is
no longer wired up; all UI that previously targeted it must migrate to
`POST /orchestrate/stream`, which returns Server‑Sent Events (SSE) with the full
runner telemetry.

Assumptions:

- The frontend already follows the MCP/OAuth contract in
  `FRONTEND_MCP_CONTRACT.md` (provider discovery, OAuth, tool pickers, etc.).
- `X-User-Id` headers and dev TLS certificates are already set up (per the
  backend README).
- Next.js ≥ 13 / React ≥ 18 with access to the modern `fetch` streaming APIs.

---

## 1. Endpoint Overview

| Field | Value |
| --- | --- |
| Method | `POST` |
| Path | `/orchestrate/stream` |
| Required headers | `Content-Type: application/json`, `Accept: text/event-stream`, `X-User-Id: <tenant>` |
| Response | `text/event-stream` feed (SSE) |

- Connections stay open until the server emits `event: response.completed` or
  `event: response.failed`. A `response` frame right before those contains the
  serialized `RunnerResult` (see `framework/orchestrator/data_types.py`).
- Always send `credentials: "include"` if your frontend relies on cookies or
  `Authorization` headers for auth.

---

## 2. Payload Schema (mirrors `OrchestrateRequest`)

Minimum viable payload:

```json
{
  "task": "Book tomorrow's noon meeting with Amy and CC finance"
}
```

Full schema:

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `task` | string | ✅ | User instruction shown in the task input box. Must be non-empty after trimming. |
| `worker` | object | ❌ | Overrides worker defaults (`engine_params`, `max_steps`, etc.). Defaults live in `DEFAULT_WORKER_CONFIG`. |
| `grounding` | object | ❌ | Overrides grounding/code-agent settings (`DEFAULT_GROUNDING_CONFIG`). Leave unset unless you expose an advanced panel. |
| `controller` | object | ❌ | Overrides VM controller host/base URL (`DEFAULT_CONTROLLER_CONFIG`). Useful only when pointing at a non-default VM. |
| `platform` | string | ❌ | Optional hint (e.g., `"windows"` or `"linux"`). |
| `enable_code_execution` | boolean | ❌ | Enables code-agent execution within the run. Defaults to `false`. |
| `tool_constraints` | object | ❌ | Controls which MCP tools the runner is allowed to call. See below. |

`tool_constraints` structure (see `ToolConstraints` dataclass):

```jsonc
{
  "mode": "auto",              // or "custom"
  "providers": ["gmail"],      // lowercase slugs from /api/mcp/auth/providers
  "tools": ["gmail_send_email"]// action names from /api/mcp/auth/tools/available
}
```

- `mode: "auto"` exposes every authorized provider after OAuth.
- `mode: "custom"` locks the runner to the supplied providers/tools. You can
  omit `providers` if you only want to send explicit action names.
- Empty arrays are treated as `null`, so only include values that matter.

### 2.1 Tool Name Reference (must match backend identifiers)

All tool names sent from the frontend must exactly match the backend action
identifiers declared in `framework/mcp/actions.py`. The same values are returned
via `GET /api/mcp/auth/tools/available`. Current mapping:

| Provider slug | Action name (use verbatim) |
| --- | --- |
| `slack` | `slack_post_message`, `slack_search_messages` |
| `gmail` | `gmail_send_email`, `gmail_search` |

If additional providers/actions are added later, update both
`framework/mcp/actions.py` and this table so the frontend cannot drift.

---

## 3. Building the Payload from UI State

1. **Gather the user’s task string.**
   - Trim whitespace and ensure it’s non-empty.
   - reject excessively short inputs (`< 5` chars) client-side.
2. **Snapshot tool selections.**
   - The MCP picker UI lets the user constrain providers/actions, assemble
     them into `tool_constraints`.
   - Example: user toggles Gmail + Slack plus `gmail_send_email` only → set
     `tool_constraints.mode = "custom"`, `providers = ["gmail", "slack"]`,
     `tools = ["gmail_send_email"]`.
3. **Apply advanced overrides (optional UI).**
   - Worker overrides: expose e.g. “Model” or “Max steps” dropdowns if needed.
   - Controller overrides: only when pointing at a non-default VM.
   - Grounding overrides: for debugging; most flows can skip them.
4. **Emit the final payload.**

```ts
const payload = {
  task: taskInput.trim(),
  worker: workerOverrides ?? undefined,
  grounding: groundingOverrides ?? undefined,
  controller: controllerOverrides ?? undefined,
  platform: selectedPlatform ?? undefined,
  enable_code_execution: enableCodeExecution ?? false,
  tool_constraints: buildToolConstraints(currentProviderSelections),
};
```

Drop `undefined` keys before serializing to avoid sending empty objects.

---

## 4. Posting and Streaming from the Frontend

```ts
async function streamOrchestrator(payload: Record<string, unknown>) {
  const res = await fetch(`${API_BASE}/orchestrate/stream`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
      "X-User-Id": userId,
    },
    credentials: "include",
    body: JSON.stringify(payload),
  });

  if (!res.ok || !res.body) {
    throw new Error(`Orchestrator request failed: ${res.status} ${res.statusText}`);
  }

  for await (const evt of parseSSE(res.body)) {
    switch (evt.event) {
      case "response.created":
        setRunPhase("queued");
        break;
      case "response.in_progress":
        setRunPhase("running");
        break;
      case "runner.step.started":
        appendStep(evt.data);
        break;
      case "response":
        setFinalResult(evt.data as RunnerResult);
        break;
      case "response.completed":
        setRunPhase(evt.data?.status ?? "success");
        break;
      case "response.failed":
      case "error":
        setRunPhase("failed");
        surfaceError(evt.data);
        break;
      default:
        appendTelemetry(evt);
    }
  }
}
```

- `parseSSE` can reuse the helper from `STREAMING_GUIDE.md` §3.
- Keep both server and frontend HTTPS/TLS origins added to CORS
  (`server.py` → `CORSMiddleware`).
- Abort the request (via `AbortController`) when the task input box is reset.

---

## 5. UI/State Recommendations

1. **Task box controls**
   - Disable the “Run” button until MCP auth + tool metadata load.
   - Show the selected tool scope (e.g., badges “Gmail · Slack · 3 tools”).
   - Surface validation errors inline (missing task text, no authorized tools).
2. **Run lifecycle**
   - `idle` → `queued` (after `response.created`) → `running`
     (`response.in_progress`) → `success`/`failed`/`timeout`
     (from `response.completed` or `response.failed`).
   - Show streaming step cards fed by `runner.step.*` events.
   - Display the final `RunnerResult` summary (task, status, steps array).
3. **Retry & cancellation**
   - Hook an “Abort” button to an `AbortController` to cancel the fetch and
     reset UI state.
   - Provide a “Retry last task” convenience action that reuses the previous
     payload.
4. **Tool scope confirmation**
   - When `tool_constraints.mode === "custom"`, confirm the server echoed the
     same set via telemetry (`runner.tools.configured` events). If they differ,
     show a warning so the user understands which tools actually ran.

---

## 6. Error Handling & Observability

| Scenario | Symptom | Frontend action |
| --- | --- | --- |
| Missing `task` | Server responds 400 JSON | Block send with client-side validation; highlight input. |
| Unauthorized (`401/403`) | Fetch rejects before SSE begins | Prompt user to re-auth / refresh. |
| MCP auth missing | Worker errors early, surfaces via `response.failed` | Relay `detail` message, prompt user to connect providers (the MCP contract endpoints fill the UI). |
| Network drop mid-run | SSE stream closes without `response.completed` | Transition to `failed`, offer “Retry”. |
| Tool constraint validation error | Server returns 400 with message like “tool_constraints.mode must be …” | Ensure UI only allows valid strings (`auto`/`custom`) and lower-case providers. |

Log/telemetry tips:

- Tag each run with a client-generated `run_id` stored in React state. Include
  it in analytics events and SSE logs so you can correlate frontend/backends.
- Mirror key SSE events to the browser console when `NODE_ENV === "development"`
  for easier debugging.

---

## 7. Migration Checklist (from `/orchestrate/runs`)

1. Replace all fetches to `/orchestrate/runs` with the flow above that calls
   `POST /orchestrate/stream`.
2. Remove any polling code that waited for `/orchestrate/runs/{id}`; the SSE
   stream now delivers final results directly.
3. Ensure your CI/dev environments add both the HTTP and HTTPS frontend origins
   to the backend CORS allowlist.
4. Confirm that MCP provider selection UI feeds into `tool_constraints`.
5. Validate that the UI handles `response.failed` gracefully (show message,
   allow retry).

Once these steps are complete, the main task input box drives the exact payload
shape expected by `framework/api/server.py`, ensuring a single, fully-streamed
execution path across dev and production.
