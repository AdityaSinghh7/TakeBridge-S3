# Live Run Events & Process Packaging

This captures how run-event streaming works today, how to move to push-based delivery, and how to run server + worker together under one command.

## Current run-events path (`/api/runs/{run_id}/events`)
- Client opens **one SSE connection** to this endpoint.
- The server polls Supabase every ~1s for `run_events` with `run_id`, ordered by `ts` ascending, tracking `last_ts`, and streams all new events to the client. It stops after the run reaches a terminal status.
- Client does **not** re-poll; polling is internal to the server handler. Per-connection polling means N clients ⇒ N polls/sec, with ~1s latency.

## Push-based alternatives (recommended for production)
- **Supabase Realtime:** Have the frontend subscribe directly to `run_events` (filtered by `run_id`) using the user JWT. If keeping the SSE endpoint, bridge Realtime once per `run_id` and fan out to connected clients (no per-client polling).
- **Postgres LISTEN/NOTIFY bridge:** When inserting `run_events`, also `NOTIFY run_event` with payload `{run_id, ts, event}`. The API keeps one listener task and fans out to SSE/WebSocket clients. On connect, fetch historical events once, then rely on push.
- **Shared poller (interim):** One poller per `run_id` that fans out to all SSE clients. Better than per-client polling but still pull-based.

Recommendation: move to a push model (Supabase Realtime or LISTEN/NOTIFY bridge) to cut latency and Supabase load.

## Packaging server + worker under one command

Use a simple supervisor so each runs as its own process but starts with a single command and can be scaled independently.

### Procfile (honcho/foreman)
```
web: uvicorn server.api.server:app --host 0.0.0.0 --port 8000
runtime: uvicorn runtime.api.server:app --host 0.0.0.0 --port 8001
worker: python -m worker.run_worker
```
Run: `honcho start` (or `foreman start`). To scale, e.g. `honcho start -c web=2,worker=4`. In Docker, set `CMD ["honcho", "start"]`.

### supervisord (alternative)
```
[program:web]
command=uvicorn server.api.server:app --host 0.0.0.0 --port 8000
autostart=true
autorestart=true

[program:runtime]
command=uvicorn runtime.api.server:app --host 0.0.0.0 --port 8001
autostart=true
autorestart=true

[program:worker]
command=python -m worker.run_worker
autostart=true
autorestart=true
```
Run: `supervisord -c supervisord.conf`.

### Env expectations
- `DB_URL` should point to Postgres if you want NOTIFY-based wakeups.
- Supabase keys (`SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`) must be set for run_events/workflow CRUD.
- VM config (`AWS_*`, controller ports, etc.) must be set for the worker path.
