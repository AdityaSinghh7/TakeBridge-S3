# User Metadata Plan (users.metadata)

## Scope and current data sources
- `users` table (registry, `mcp_agent/registry/db_models.py`) is minimal today (id, created_at). It is created in `alembic/versions/df7656705064_initial_schema.py`.
- Workflow ownership and run state live under `profiles`, `workflows`, `workflow_runs` (see `shared/db/models.py` and migrations under `alembic/versions/`).
- Run lifecycle signals:
  - Enqueue and credit debit: `server/api/routes_workflows.py` (RUN_CREDIT_COST, workflow_runs.insert_run, profiles.debit_credits).
  - Claim + start: `worker/run_worker.py` (status=running, started_at, claimed_by, last_heartbeat_at).
  - Terminal status updates: `server/api/server.py` and `worker/run_worker.py`.
  - Heartbeats: `shared/db/workflow_runs.touch_run()` (called on persisted run events).
- Error detail sources:
  - `run_events` table (persisted via `server/api/server.py` with `PERSISTED_EVENTS` whitelist).
  - `workflow_runs.summary` (set by server status updates).
  - `workflow_runs.agent_states` (only fully persisted on handback in `computer_use_agent/orchestrator/runner.py`).
- Cost sources:
  - `shared/token_cost_tracker.py` writes per-run JSONL logs only; no DB persistence today.
  - Orchestrator step usage is computed in `orchestrator_agent/runtime.py` but not stored in DB.
- Credits:
  - Only current balance is stored in `profiles.credits`; debits are applied in `profiles.debit_credits()`, no ledger.
- Active workers:
  - `workflow_runs.claimed_by` and `last_heartbeat_at` are the only durable signals for worker activity.

## Requested metrics and intended sources
1) Last N workflows for a user
   - Source: `workflow_runs` ordered by `COALESCE(started_at, created_at)` with workflow_id + status.
2) Success percentage
   - Store raw counts by terminal status; compute percentage on read.
3) Last N errored workflows
   - Source: `workflow_runs` where status in error-set; plus error details from `run_events` and summary.
4) Error reason + point of last error
   - Primary: `run_events` (mcp.step.recorded errors, mcp.action.failed, runner.step.completed with status=failed, etc).
   - Fallback: `workflow_runs.summary` and last known status.
   - Gap: orchestrator exceptions are not in `PERSISTED_EVENTS`.
5) Total $ spent (token cost)
   - Must persist TokenCostTracker output or per-run usage to DB.
6) Credits used
   - Persist per-run credits_cost; aggregate to total credits spent.
7) Average workflow duration
   - Use `started_at` and `ended_at`; store sum and count, compute avg on read.
8) Currently active workers
   - Derived from running runs with recent `last_heartbeat_at`, grouped by `claimed_by`.

## Canonical users.metadata schema (v1)
Store raw counters and small windows, not precomputed rates/averages.

```json
{
  "version": 1,
  "updated_at": "2025-01-01T12:00:00Z",
  "run_counters": {
    "total": 0,
    "terminal": 0,
    "success": 0,
    "error": 0,
    "attention": 0,
    "cancelled": 0,
    "partial": 0
  },
  "duration_ms": {
    "count": 0,
    "total": 0
  },
  "credits": {
    "spent_total": 0,
    "last_debit_at": null
  },
  "costs": {
    "input_cached": 0,
    "input_new": 0,
    "output": 0,
    "cost_usd_total": 0.0,
    "last_cost_update_at": null
  },
  "recent_runs": [
    {
      "run_id": "uuid",
      "workflow_id": "uuid",
      "status": "queued|running|success|error|attention|cancelled|partial",
      "trigger_source": "manual|...",
      "created_at": "ISO-8601",
      "started_at": "ISO-8601|null",
      "ended_at": "ISO-8601|null",
      "duration_ms": 12345,
      "summary": "string|null",
      "credits_cost": 10,
      "llm_cost_usd": 0.1234
    }
  ],
  "recent_errors": [
    {
      "run_id": "uuid",
      "workflow_id": "uuid",
      "status": "error|attention",
      "ended_at": "ISO-8601",
      "error_reason": "string",
      "error_point": {
        "event": "mcp.step.recorded|runner.step.completed|orchestrator.task.failed",
        "step_id": "string|null",
        "tool": "provider.tool|null",
        "message": "string|null"
      },
      "event_ts": "ISO-8601"
    }
  ],
  "active": {
    "runs": [
      {
        "run_id": "uuid",
        "claimed_by": "worker@host:pid",
        "started_at": "ISO-8601",
        "last_heartbeat_at": "ISO-8601"
      }
    ],
    "workers": [
      {
        "claimed_by": "worker@host:pid",
        "run_ids": ["uuid"],
        "last_heartbeat_at": "ISO-8601"
      }
    ]
  },
  "ingestion": {
    "last_run_update_at": "ISO-8601|null",
    "last_event_ts": "ISO-8601|null"
  }
}
```

Notes:
- Keep `recent_runs` and `recent_errors` capped to N (configurable).
- Avoid storing large payloads (no full trajectories, no agent_states).
- Avoid precomputed rates; keep raw counters + sums.

## Instrumentation gaps and fixes
1) Add `users.metadata` column
   - Alembic migration with JSON/JSONB default `{}`.
   - Update `mcp_agent/registry/db_models.User` to include a JSONType column.
   - Consider updating `alembic/env.py` to include registry metadata or keep migration manual.
2) Persist per-run cost in DB
   - Store incremental usage under `workflow_runs.metadata._tb.token_usage` + `workflow_runs.metadata._tb.llm_cost_usd`.
   - Update users metadata totals directly from `TokenCostTracker` deltas using `RUN_LOG_ID`.
3) Persist credits usage
   - Store `credits_cost` in `workflow_runs.metadata._tb` at enqueue.
   - Optional: add `credits_ledger` table for idempotent debits by run_id.
4) Error detail capture
   - Extend `PERSISTED_EVENTS` to include server error events (`response.failed`, `error`).
   - Add a helper to extract last error event per run from `run_events`.
5) Active worker signals
   - Define heartbeat staleness threshold (ex: 2-5 min).
   - Use `workflow_runs.last_heartbeat_at` + `claimed_by` to maintain active list.

## Persistence points (where to update users.metadata)
1) Enqueue (queued)
   - File: `server/api/routes_workflows.py`
   - Actions: append to `recent_runs`, increment `run_counters.total`, store `credits_cost`.
2) Claim/start (running)
   - File: `worker/run_worker.py` (after successful claim)
   - Actions: update run entry status, `started_at`, and `active.runs/workers`.
3) Terminal status update (success/error/attention/cancelled/partial)
   - Files: `server/api/server.py` and `worker/run_worker.py`
   - Actions: update run entry, increment terminal counters, remove from active, update duration sums,
     append to `recent_errors` when status in error-set, store error snapshot + llm_cost.
4) Error events (run_events)
   - File: `server/api/server.py` emitter or a new run_events consumer
   - Actions: update `recent_errors.last_error` for the run (idempotent, latest by ts).

## Robustness and correctness
- Use a single metadata update helper with `SELECT ... FOR UPDATE` to avoid lost updates.
- Guard against double counting by storing per-run status in `recent_runs` entries
  and only increment counters on the first terminal transition.
- Normalize user_id consistently (Supabase UUIDs vs normalized IDs).
- Always cap arrays and drop old entries by timestamp or order.

## Backfill and reconciliation
1) One-time backfill script:
   - Rebuild `users.metadata` from `workflow_runs`, `run_events`, `profiles`.
   - Recompute counters, durations, and populate recent runs/errors.
2) Periodic reconcile job:
   - Fix drift (missed events or failures) and trim stale active runs.
   - Validate cost/credits totals against per-run metrics.

## Testing and validation
- Unit tests for metadata update helper (idempotency, concurrency, trimming).
- Integration tests for enqueue -> running -> success/error paths.
- Tests for error snapshot extraction from run_events.
- Verify cost attribution per run with concurrent runs.

## Open decisions to confirm
- Store metadata in `users` (registry) vs `profiles` (workflow ownership). 
  - Answer: Lets use the `profiles` table!
- Choose cost persistence strategy (workflow_runs.metadata vs new metrics table).
  - Answer: let's persist cost per `run`, so persisting in the workflow_runs table would work. 
- Define error status set and success classification for "success %" (treat "partial"?).
  - Answer: So, if / when a run's status goes from `running` to `error`, then we should treat that as error status, success classification should be error runs / completed runs * 100, and partial won't be counted in `completed` as they are probably either `running` or `attention required`. 
