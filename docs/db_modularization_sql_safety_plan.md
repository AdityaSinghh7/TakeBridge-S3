# Plan

Refactor database access so API route handlers do **zero** direct SQL and instead call `shared/db/*` functions that use SQLAlchemy Core/ORM and **parameter binding** everywhere. The goal is *no functionality changes* (same responses + same DB side effects), while substantially reducing SQL-injection risk and making DB access consistent and testable.

## Requirements
- No behavior changes: keep response payloads, error codes, commit timing, and side effects the same.
- SQL-injection hardening: prohibit interpolating user input into SQL strings; use SQLAlchemy Core/ORM binds or `text()` with named parameters.
- Explicit authorization guards: DB functions that fetch/update user-owned rows must require `user_id` and enforce it in the query.
- Keep SQLite dev + Postgres prod compatibility (JSON columns, timestamps, `pg_notify` behavior).
- Keep routing and auth logic in API layer; move *only* DB CRUD/join logic.

## Scope
**In**
- API modules that currently open sessions and run queries:
  - `server/api/routes_workflows.py`
  - `server/api/routes_guac_auth.py`
  - `server/api/routes_mcp_auth.py` (debug endpoint + helper)
  - `server/api/server.py` (run lifecycle helpers + `/runs/{run_id}/resume`)
- API helper modules that do DB ops and are called by endpoints:
  - `server/api/run_attachments.py`
  - `server/api/run_drive.py`
  - `server/api/run_artifacts.py`
- Existing DB layer:
  - `shared/db/engine.py`
  - `shared/db/models.py`
  - `shared/db/workflow_runs.py`
  - `shared/db/crud.py`
  - `mcp_agent/registry/crud.py`

**Out**
- Any schema changes or alembic migration changes.
- Large behavioral changes (pagination semantics, validation strictness, response formats).
- Replacing Supabase client usage in endpoints that already use it (unless needed for joins/consistency).

## Current Findings (Audit)

### 1) Endpoints with direct DB ops in the handler

#### `server/api/routes_workflows.py`
These route handlers open `SessionLocal()` and perform DB ops directly:
- `POST /api/workflows/{workflow_id}/run` (`enqueue_workflow_run`)
  - Updates `profiles.credits` (raw SQL `UPDATE ... RETURNING`)
  - Inserts into `workflow_runs` (raw SQL `INSERT`)
  - Inserts `WorkflowRunFile` rows (ORM `db.add(...)`)
  - Calls `pg_notify(...)` when `DB_URL` is Postgres (raw SQL)
- `GET /api/workflows/{workflow_id}/files` (`list_workflow_files`)
  - Selects `WorkflowFile` rows via SQLAlchemy Core/ORM
- `POST /api/workflows/{workflow_id}/files/request-upload` (`request_workflow_file_upload`)
  - Inserts `WorkflowFile` (ORM)
- `POST /api/workflows/{workflow_id}/files/{file_id}/finalize` (`finalize_workflow_file`)
  - Reads and updates `WorkflowFile` (ORM)
- `DELETE /api/workflows/{workflow_id}/files/{file_id}` (`delete_workflow_file`)
  - Reads and deletes `WorkflowFile` (ORM)
- `GET /api/runs/{run_id}/vm` (`get_run_vm`)
  - Joins `workflow_runs` + `vm_instances` via raw SQL
- `GET /api/runs/{run_id}/artifacts` (`list_run_artifacts`)
  - Verifies run ownership in `workflow_runs` via raw SQL
  - Selects `WorkflowRunArtifact` via ORM
- `POST /api/runs/{run_id}/commit-drive-changes` (`commit_drive_changes`)
  - Verifies run ownership in `workflow_runs` via raw SQL
  - Selects `WorkflowRunDriveChange` via ORM
- `GET /api/runs/{run_id}/drive-file` (`download_drive_file`)
  - Reads from `workflow_run_files` via raw SQL
  - Calls `_get_run_controller_base_url(...)` which reads `workflow_runs.environment` via raw SQL
- `GET /api/runs` (`list_runs`)
  - Builds a query string and executes `text(query)` with bound params (safe today, but still raw SQL in handler)

Other endpoints in this file (`/workflows`, `/folders`, etc.) use the Supabase client and do not execute raw SQL in-process.

#### `server/api/routes_guac_auth.py`
- `POST /guac/runs/{run_id}/token` (`get_run_guac_token`)
  - Joins `workflow_runs` + `vm_instances` via raw SQL
- `POST /guac/workspace/token` (`get_workspace_guac_token`)
  - Reads `Workspace` via ORM query (`db.query(Workspace)...`)

#### `server/api/routes_mcp_auth.py`
- `GET /api/mcp/auth/_debug/db` (`debug_db`)
  - Uses `session_scope()` and counts rows via ORM

#### `server/api/server.py`
- `POST /runs/{run_id}/resume` (`resume_run`)
  - Selects `workflow_runs` (raw SQL) and later updates status to `queued` (raw SQL)

Additionally, several *helpers called by endpoint flows* do DB writes/reads directly:
- `_touch_run_row(...)` updates `workflow_runs.last_heartbeat_at`
- `_update_run_status(...)` updates `workflow_runs.status/summary/ended_at`
- `_resolve_controller_session(...)` reads `workflow_runs.environment`
- `_provision_controller_session(...)` inserts into `vm_instances` and updates `workflow_runs.vm_id`

### 2) API helper modules that do DB ops (not route handlers, but in `server/api/`)
- `server/api/run_attachments.py`
  - Reads and updates `workflow_run_files` statuses via raw SQL
- `server/api/run_drive.py`
  - Reads and updates `workflow_run_files` via raw SQL
  - Deletes from `workflow_run_drive_changes` via raw SQL
  - Inserts `WorkflowRunDriveChange` via ORM
- `server/api/run_artifacts.py`
  - Deletes from `workflow_run_artifacts` via raw SQL
  - Inserts `WorkflowRunArtifact` via ORM
  - Reads and updates `workflow_runs.environment` via raw SQL

### 3) Existing DB layer (`shared/db/`) coverage + gaps
- `shared/db/engine.py`: `DB_URL`, `engine`, `SessionLocal`, `session_scope()`.
- `shared/db/models.py`: models for MCP registry + `Workspace` + file tables (`WorkflowFile`, `WorkflowRunFile`, `WorkflowRunArtifact`, `WorkflowRunDriveChange`).
  - **Gap:** no models for `profiles`, `folders`, `workflows`, `workflow_runs`, `run_events`, `vm_instances` even though these tables exist (see alembic).
- `shared/db/workflow_runs.py`: safe, parameterized helpers for `agent_states` and `mark_run_attention`.
  - **Gap:** environment/status/vm_id/heartbeat helpers are duplicated in API/worker code instead of living here.
- `shared/db/crud.py` and `mcp_agent/registry/crud.py`: safe SQLAlchemy Core/ORM CRUD for MCP registry.

### 4) SQL-injection posture today
- The repo appears to already avoid the worst patterns (no `text(f"...")`/`execute(f"...")` patterns found).
- Most raw SQL uses `:named_params` and passes a dict — good.
- The remaining risk is *regression risk* (future edits introducing interpolation) and *inconsistency* (ad-hoc raw SQL spread across handlers).

## Target Design

### DB-access conventions
- Route handlers should:
  - parse/validate inputs
  - enforce auth (current_user)
  - call DB-layer functions with primitive values
  - format the response
- DB-layer functions should:
  - accept `db: Session` explicitly (preferred), or accept optional `db` and create/close when omitted (match existing `shared/db/workflow_runs.py` pattern)
  - enforce `user_id` scoping when rows are user-owned
  - use SQLAlchemy Core/ORM bind parameters everywhere
  - avoid returning ORM objects across layers unless the caller is in the same module (return dicts/typed dataclasses where helpful)

### Proposed module layout (within `shared/db/`)
- Extend `shared/db/models.py`
  - Add missing table models: `Profile`, `Folder`, `Workflow`, `WorkflowRun`, `RunEvent`, `VMInstance`
  - Keep JSON typing consistent with existing `JSONType` pattern
- Extend `shared/db/workflow_runs.py`
  - Add run lifecycle helpers (status, heartbeat, environment, vm binding, ownership checks)
- Add modules (new)
  - `shared/db/profiles.py` (credit debit helpers)
  - `shared/db/workflow_files.py` (CRUD for `WorkflowFile`)
  - `shared/db/workflow_run_files.py` (CRUD for `WorkflowRunFile`)
  - `shared/db/workflow_run_artifacts.py` (CRUD for `WorkflowRunArtifact`)
  - `shared/db/workflow_run_drive_changes.py` (CRUD for `WorkflowRunDriveChange`)
  - `shared/db/vm_instances.py` (CRUD for `VMInstance`)

### Guardrails against SQL injection
- Prefer SQLAlchemy Core/ORM (`select/update/insert/delete`) over raw SQL strings.
- If raw SQL is unavoidable (e.g., `pg_notify`), wrap it:
  - Create `shared/db/sql.py` with a small helper like `execute_text(db, sql: str, params: dict)` that:
    - rejects suspicious formatting tokens (`{`, `}`, `%(`) to prevent accidental f-string/format usage
    - requires `params` and uses `sqlalchemy.text(sql)`
- Add a lightweight repo check (CI or pre-commit):
  - A script (e.g., `scripts/check_sql_safety.py`) that fails on patterns like `text(f`, `.execute(f`, `.format(` adjacent to SQL keywords.

## Detailed Refactor Map (what to extract, where)

### A) `server/api/routes_workflows.py`
- `enqueue_workflow_run(...)`
  - Extract to DB layer:
    - `profiles.debit_credits(db, user_id, cost) -> credits_remaining | None`
    - `workflow_runs.insert_run(db, run_id, workflow_id, user_id, folder_id, trigger_source, metadata_json, environment_json)`
    - `workflow_run_files.insert_run_files_for_uploads(...)` (for uploaded files)
    - `workflow_run_files.insert_run_files_for_drive_paths(...)` (for drive files)
    - `workflow_runs.notify_run_queued(db, run_id, user_id)` (Postgres-only)
- `list_workflow_files(...)`
  - `workflow_files.list_for_workflow(db, workflow_id, user_id)`
- `request_workflow_file_upload(...)`
  - `workflow_files.create_pending_file(db, workflow_id, user_id, storage_key, filename, content_type, size_bytes, checksum, metadata)`
- `finalize_workflow_file(...)`
  - `workflow_files.get_for_user(db, workflow_id, user_id, file_id)`
  - `workflow_files.finalize_file(db, file_id, size_bytes, checksum, content_type, metadata)`
- `delete_workflow_file(...)`
  - `workflow_files.get_for_user(...)`
  - `workflow_files.delete(db, file_id)`
- `get_run_vm(...)`
  - `workflow_runs.get_run_vm_endpoint(db, run_id, user_id)`
    - encapsulate join to `vm_instances`
    - encapsulate “endpoint may be in environment JSON” fallback
- `list_run_artifacts(...)`
  - `workflow_runs.assert_owned(db, run_id, user_id)`
  - `workflow_run_artifacts.list_for_run(db, run_id)`
- `commit_drive_changes(...)`
  - `workflow_runs.assert_owned(db, run_id, user_id)`
  - `workflow_run_drive_changes.list_for_run(db, run_id, user_id)`
- `download_drive_file(...)`
  - `workflow_run_files.get_drive_file_row(db, run_id, user_id, drive_path)`
  - replace `_get_run_controller_base_url(...)` with `workflow_runs.get_controller_base_url(db, run_id, user_id)`
- `list_runs(...)`
  - `workflow_runs.list_runs_with_workflow(db, user_id, status_filter, folder_id, limit)`

### B) `server/api/routes_guac_auth.py`
- `get_run_guac_token(...)`
  - Replace inline join query with `workflow_runs.get_run_vm_endpoint(db, run_id, user_id)` (same helper as `/api/runs/{run_id}/vm`).
- `get_workspace_guac_token(...)`
  - Optional: move workspace query to `shared/db/workspaces.py` (thin wrapper), or keep as-is since it is already ORM + parameterized.

### C) `server/api/server.py`
Move run lifecycle DB helpers out of the API module:
- `_touch_run_row(run_id)` -> `workflow_runs.touch_run(db, run_id)`
- `_update_run_status(run_id, status, summary)` -> `workflow_runs.set_status(db, run_id, status, summary)`
- `_resolve_controller_session(...)` DB read -> `workflow_runs.get_environment(db, run_id)`
- `_provision_controller_session(...)` DB writes ->
  - `vm_instances.insert_instance(db, vm_id, run_id, status, provider, spec_json, endpoint_json)`
  - `workflow_runs.set_vm_id(db, run_id, vm_id)`
- `/runs/{run_id}/resume` (`resume_run`)
  - `workflow_runs.get_resume_snapshot(db, run_id)` (id/user_id/status/agent_states/environment)
  - `workflow_runs.set_status(db, run_id, 'queued', updated_at=now)`

### D) `server/api/run_attachments.py`
- Replace inline `workflow_run_files` SQL with:
  - `workflow_run_files.list_pending_non_drive_files(db, run_id)`
  - `workflow_run_files.mark_failed(db, run_file_id, error, updated_at)`
  - `workflow_run_files.mark_ready(db, run_file_id, vm_path, updated_at)`

### E) `server/api/run_drive.py`
- Replace inline SQL with:
  - `workflow_run_files.list_drive_files_for_run(db, run_id)`
  - `workflow_run_files.mark_failed(...)` / `mark_ready(...)` (drive-specific fields: `drive_path`, `r2_key`, `checksum`, etc.)
  - `workflow_run_drive_changes.delete_for_run_path(db, run_id, path)`
  - `workflow_run_drive_changes.insert_change(db, ...)`

### F) `server/api/run_artifacts.py`
- Move environment helpers into `shared/db/workflow_runs.py`:
  - `get_environment(db, run_id)`
  - `merge_environment(db, run_id, patch)`
- Move artifacts CRUD into `shared/db/workflow_run_artifacts.py`:
  - `delete_for_run_filename(db, run_id, filename)`
  - `insert_artifact(db, ...)`

## Implementation Plan (Phased)

## Action items
[ ] Add missing SQLAlchemy models (`profiles`, `folders`, `workflows`, `workflow_runs`, `run_events`, `vm_instances`) to `shared/db/models.py` based on alembic schemas.
[ ] Add/extend DB modules in `shared/db/` for `profiles`, `workflow_runs`, `vm_instances`, `workflow_files`, `workflow_run_files`, `workflow_run_artifacts`, `workflow_run_drive_changes`.
[ ] Refactor `server/api/routes_workflows.py` to call DB functions (no inline SQL / `SessionLocal()` queries beyond session creation).
[ ] Refactor `server/api/routes_guac_auth.py` to reuse DB helper(s) for run→endpoint lookup.
[ ] Refactor `server/api/server.py` to import DB helpers for run lifecycle (heartbeat/status/environment/vm binding) and remove raw SQL from helpers.
[ ] Refactor `server/api/run_attachments.py`, `server/api/run_drive.py`, `server/api/run_artifacts.py` to use DB functions.
[ ] Add SQL-safety guardrails (`shared/db/sql.py` wrapper + `scripts/check_sql_safety.py`).
[ ] Validate behavior:
  - run existing tests (e.g., `pytest`)
  - smoke test the impacted endpoints
  - verify DB side effects for: enqueue run, resume run, attachment staging, drive staging, artifact export.

## Testing and validation
- Run unit/integration tests if present: `pytest`.
- Add minimal tests for DB helpers (optional but recommended):
  - use SQLite temp DB + apply migrations (`alembic upgrade head`) + exercise each new DB function with known inputs.
- Add a regression scan: ensure repo has **no** `text(f"...`) / `.execute(f"...`) patterns.

## Risks and edge cases
- Transaction boundaries: some code currently commits per-row (attachments/drive staging). Preserve those semantics unless explicitly agreed.
- JSON column type differences (SQLite vs Postgres): keep serialization consistent and avoid relying on dialect-specific JSON behavior.
- Postgres-only `pg_notify`: must remain conditional on `DB_URL.startswith("postgres")`.
- Ownership checks: ensure all new DB helpers that fetch/update user-owned rows require `user_id` and filter on it.

## Open questions
- Should we add full ORM models for `workflow_runs`/`vm_instances`/`profiles`/`workflows` and convert all raw SQL to Core/ORM, or keep raw SQL but centralize it (both can be safe with binds)? 
  - Answer: keep raw SQL but centralize it. Keep it safe with binds.
- Is `DB_URL` always pointing at the same database that Supabase client reads/writes (prod) and the SQLite file (dev)? If not, join queries (like `/api/runs`) need special handling.
  - Answer: Yes DB_URL is always pointing at the same Supabase database. The Supabase db is our only DB, the SQLite db is deprecated. 
- Do you want the MCP registry CRUD to have a single canonical location (`shared/db/crud.py` vs `mcp_agent/registry/crud.py`), or keep both?
  - Answer: Have a single canonical location. 
