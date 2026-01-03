# Runtime vs Control-Plane Decoupling Plan

## Goals
- Decouple long-running agent execution from the main API so runtime load does not block non-runtime requests.
- Preserve existing external behavior and API contracts for clients.
- Keep all database reads/writes in a dedicated control-plane service.
- Enable independent scaling of runtime vs control-plane capacity.

## Non-goals
- No functional changes to orchestration, workflow semantics, or data models.
- No DB schema changes required for the initial split.
- No new UI behavior or client-side contract changes.

## Current state (key runtime + data coupling points)
- Runtime execution lives in `server/api/server.py`:
  - `/orchestrate`, `/orchestrate/stream`, `/internal/runs/{run_id}/execute`, `/runs/{run_id}/resume`.
  - `_create_streaming_response()` runs the orchestrator, persists events, updates run status, and touches DB.
  - `_resolve_controller_session()` provisions VM instances and writes VM info to DB.
  - Drive staging/commit uses `server/api/run_drive.py`, which mixes VM work and DB updates.
- Worker dispatch is in `worker/run_worker.py`:
  - Claims runs via DB and calls `/internal/runs/{run_id}/execute`.
- Non-runtime APIs live in `server/api/routes_workflows.py`, `server/api/routes_drive.py`, `server/api/routes_mcp_auth.py`, etc.:
  - Run enqueue, file upload, credit debits, metadata updates, OAuth, storage operations.
  - Some VM-touching endpoints exist in `server/api/routes_workflows.py` (drive file streaming, commit-drive-file).
- Compose/planning endpoint in `server/api/routes_compose_task.py` invokes orchestrator planning logic.

## Target architecture

### Services
1) **Control-plane service (API + DB)**
   - Owns auth, workflow/run CRUD, file/drive CRUD, credits, metadata, OAuth.
   - Owns all reads/writes to Postgres/Supabase.
   - Proxies runtime endpoints (or routes clients directly) without doing heavy work.
   - Exposes internal endpoints for runtime to fetch run context and persist runtime results.

2) **Runtime service (agent orchestration + VM operations)**
   - Owns orchestration execution, streaming, VM controller calls, handback inference.
   - Does not touch DB directly; uses control-plane internal API for persistence.

3) **Worker service (dispatcher)**
   - Claims queued runs from DB (control-plane responsibility).
   - Calls runtime service to execute runs.

### High-level flow
```
Client -> Control-plane API
  - enqueue run -> DB
  - list/read/update metadata -> DB
Worker -> Control-plane DB -> Runtime service
Runtime service -> Control-plane internal API -> DB
Runtime service -> Client (SSE for /orchestrate/stream) [direct or via proxy]
```

## Service responsibilities (proposed mapping)

### Runtime service (move or proxy from current code)
- From `server/api/server.py`:
  - `/orchestrate`, `/orchestrate/stream`, `/internal/runs/{run_id}/execute`, `/runs/{run_id}/resume`.
  - Orchestrator execution (`OrchestratorRuntime`) and SSE emission.
  - VM provisioning/lookup (`_resolve_controller_session`, `_provision_controller_session`).
  - Run drive staging/commit via VM controller (`server/api/run_drive.py`).
- From `server/api/routes_compose_task.py`:
  - `/compose_task` (LLM-based plan composition).
- From `server/api/routes_workflows.py` (runtime-only VM work):
  - `/runs/{run_id}/drive-file` (VM file streaming).
  - `/runs/{run_id}/commit-drive-file` (upload VM file to storage).

### Control-plane service (keep in current API)
- Auth, OAuth, MCP, user metadata, workflow CRUD:
  - `server/api/auth.py`, `server/api/routes_mcp_auth.py`, `server/api/routes_mcp_tools.py`,
    `server/api/routes_user_metadata.py`, `server/api/route_composio_redirect.py`, `server/api/routes_guac_auth.py`.
- Workflow queueing and DB-backed operations:
  - `server/api/routes_workflows.py` enqueue, list, file uploads, drive changes, run listing, credits.
  - `server/api/routes_drive.py` drive storage operations (R2).
- Worker remains with DB access for claiming runs.

## Internal control-plane API (runtime-facing)
These endpoints are for service-to-service use only and replace direct DB calls in runtime.

Implemented contract (all require internal auth token):
- `GET /internal/runs/{run_id}/context`
  - Returns: `run_id`, `workflow_id`, `user_id`, `metadata`, `environment`, `tool_constraints`, `endpoint`.
- `GET /internal/runs/{run_id}/resume-context`
  - Returns: `user_id`, `status`, `agent_states`, `environment`.
- `POST /internal/runs/{run_id}/events`
  - Body: `{ event, message, payload }` (persist into `run_events` + touch heartbeat).
- `POST /internal/runs/{run_id}/status`
  - Body: `{ status, summary }` (updates `workflow_runs.status/summary/ended_at`).
- `POST /internal/runs/{run_id}/environment`
  - Body: `{ patch }` (merges into `workflow_runs.environment`).
- `POST /internal/runs/{run_id}/vm`
  - Body: `{ vm_id, endpoint, provider, spec }` (register VM + set `workflow_runs.vm_id`).
- `POST /internal/runs/{run_id}/agent-states`
  - Body: `{ patch, path? }` (merge into `workflow_runs.agent_states`).
- `GET /internal/runs/{run_id}/drive-files?ensure_full=true|false`
  - Returns: `{ files[] }` (drive file rows; can auto-create full-drive list).
- `POST /internal/runs/{run_id}/drive-files/status`
  - Body: `{ file_id, status, vm_path, size_bytes, checksum, content_type, r2_key, drive_path, error? }`.
- `GET /internal/runs/{run_id}/drive-changes`
  - Returns: `{ user_id, changes[], drive_files[] }`.
- `POST /internal/runs/{run_id}/drive-changes/upsert`
  - Body: `{ changes[], new_files[] }`.
- `POST /internal/runs/{run_id}/drive-changes/status`
  - Body: `{ path, status, error? }`.
- `GET /internal/users/{user_id}/mcp-capabilities?force_refresh=true|false`
  - Returns: MCP provider/tool inventory used by `/compose_task`.

## Detailed implementation plan

### Phase 1: Extract runtime service (minimal behavior change)
- Create a new runtime app (e.g., `runtime/api/server.py`).
  - Move orchestration endpoints and helpers from `server/api/server.py`.
  - Move `/compose_task` from `server/api/routes_compose_task.py`.
  - Move `server/api/handback_inference.py`, `server/api/orchestrator_adapter.py`, `server/api/controller_client.py`.
  - Keep functionality identical; allow temporary DB access until Phase 2.
- Add a new process entry (Procfile or deployment):
  - `runtime: uvicorn runtime.api.server:app --host 0.0.0.0 --port 8001 ...`
- Add a control-plane proxy layer (optional but recommended):
  - Keep the public API path the same by proxying runtime endpoints from control-plane.
  - Use an env var like `RUNTIME_BASE_URL` to toggle direct vs proxy.

### Phase 2: Move DB access out of runtime
- Implement control-plane internal endpoints listed above.
- Create a small runtime client (`shared/internal_control_plane_client.py`) with:
  - Token auth (reuse `INTERNAL_API_TOKEN`).
  - Retry/backoff for transient errors.
  - Typed helpers: `get_run_context()`, `persist_event()`, `update_status()`, `merge_environment()`.
- Replace runtime DB calls:
  - `_persist_run_event`, `_update_run_status`, `_touch_run_row`, `_merge_run_environment`.
  - VM provisioning writes (`vm_instances.insert_vm_instance`, `workflow_runs.set_vm_id`).
  - Handback resume writes (agent_states merge + status updates).
- Result: runtime does not import `shared.db` or call Supabase directly.

### Phase 3: Split run-drive responsibilities cleanly
- Split `server/api/run_drive.py` into:
  - Runtime VM operations: list VM files, compute hashes, upload/download via controller.
  - Control-plane data operations: read/write `workflow_run_files`, `workflow_run_drive_changes`.
- Runtime flow:
  - `GET /internal/runs/{run_id}/context` returns drive file list + storage keys.
  - Runtime stages files to VM using storage presigned URLs from control-plane.
  - Runtime posts `drive-changes` back on completion.
- Control-plane flow:
  - Owns the DB write path for drive changes and the user-facing commit/apply endpoints.

### Phase 4: Update worker dispatch
- Keep `worker/run_worker.py` as-is for DB claiming.
- Point `EXECUTOR_BASE_URL` to runtime service (or control-plane proxy).
- Ensure internal token auth remains valid between worker and runtime.

### Phase 5: Stabilize runtime load and concurrency
- Add concurrency limits in runtime:
  - Global max concurrent runs per instance (async semaphore).
  - Per-user throttling if needed.
- Ensure streaming endpoints are served by runtime only (not control-plane).
- Verify long-running SSE connections do not consume control-plane workers.

### Phase 6: Cutover + cleanup
- Gate monolith runtime codepaths behind `RUNTIME_PROXY_ENABLED=false`; proxy remains the default.
- Update docs and ops runbooks.
- Keep a feature flag to fall back to monolith if needed during rollout.

## Operational considerations
- **Auth**: Use `INTERNAL_API_TOKEN` between services; keep same header contract used by worker.
- **Service URLs**: control-plane -> runtime uses `RUNTIME_BASE_URL` (default `http://127.0.0.1:8001`); runtime -> control-plane uses `CONTROL_PLANE_BASE_URL` (default `https://127.0.0.1:8000`).
- **Concurrency limits**: set `RUNTIME_MAX_CONCURRENT_RUNS` and `RUNTIME_MAX_CONCURRENT_RUNS_PER_USER` to throttle runtime execution (0 disables limits).
- **Fallback flag**: set `RUNTIME_PROXY_ENABLED=false` to run runtime paths inside the control-plane process (monolith fallback).
- **Observability**: Preserve `RUN_LOG_ID` logging; ship logs from runtime separately.
- **Scaling**: Scale runtime independently; control-plane can remain smaller and responsive.
- **Failure modes**:
  - If runtime fails mid-run, control-plane should mark run as `error` via worker retry or a watchdog.
  - If control-plane API is down, runtime should fail fast and mark run as error via retry queue.

## Validation checklist
- Run enqueue -> worker claim -> runtime execute -> status update (success/error).
- Streaming run behavior identical to today (SSE events and final response).
- Handback resume path works end-to-end (screenshot, inference, status update).
- Drive staging and drive change commit preserved.
- Control-plane remains responsive under concurrent runs.

## Decisions (confirmed)
- Runtime endpoints are exposed via the control-plane proxy only.
- Runtime service listens on port `8001`.
- Public API contracts remain unchanged; internal runtime/control-plane contracts are additive and private.

## Execution status
- Phase 1: Completed
- Phase 2: Completed
- Phase 3: Completed
- Phase 4: Completed
- Phase 5: Completed
- Phase 6: Completed
