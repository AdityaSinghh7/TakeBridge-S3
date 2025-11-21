# MCP Agent Multi-Tenant Implementation Plan

## 0. Baseline audit
- [x] Trace every entry point that invokes `execute_mcp_task` (server, sandbox runner, CLI) and record how `user_id` reaches planner/context today. `rg` shows only docs/tests call `execute_mcp_task` today (`README.md`, `Standalone_MCP_Plan.md`, `tests/planner/*`). All external consumers must call the exported `mcp_agent.planner.execute_mcp_task`, which normalizes `user_id` to `singleton` in `mcp_agent/planner/runtime.py:214` before storing it on `PlannerContext.user_id`, propagating to budget trackers, logs, and summaries. No other entry points currently bypass this path, so user scoping is centralized but the downstream agent/registry ignores it (motivation for later steps).
- [x] Use `rg` to list all references to `_sleep_snippet`, `slack_post_message`, and `gmail_send_email/search` so later changes are scoped and testable. `_sleep_snippet` only exists in `mcp_agent/actions.py` (definitions at lines 16–47 etc.) plus a mention in `flow_doc.md`; Slack/Gmail wrappers live in `mcp_agent/actions.py:84-353` with tests under `tests/mcp_core/test_actions.py` and toolbox generators/tests (`tests/toolbox/*`). No other modules depend on their string-returning behavior, so we can safely refactor them to emit structured dicts.

## 1. Structured MCP action results
- [x] Introduce `ToolInvocationResult` in `mcp_agent/types.py` (TypedDict with `successful`, `error`, `data`, `logs`, `provider`, `tool`, `payload_keys`) to standardize tool outputs. New file now exports the canonical shape and is imported by the action wrappers.
- [x] Remove `_sleep_snippet` entirely and refactor `_invoke_mcp_tool` to emit start/fail/complete events, call `MCPAgent.current()` (user scoping still pending), and return a normalized `ToolInvocationResult`. Helper utilities `_payload_key_list`, `_structured_result`, and `_normalize_tool_response` keep payload metadata + server/tool identifiers intact (`mcp_agent/actions.py`).
- [x] Update all action wrappers (Slack send/search, Gmail send/search) and documentation to expect structured dicts instead of Python snippets; validation/unauthorized paths now return descriptive dicts and the flow doc reflects the new behavior (`mcp_agent/actions.py`, `flow_doc.md`).
- [x] Add unit tests for each action wrapper that assert success/failure paths populate `successful`, `error`, `provider`, `tool`, and sorted `payload_keys` (`tests/mcp_core/test_actions.py`). Tests now inspect the structured results instead of `"import time"` strings.

## 2. Tenant-aware MCPAgent lifecycle
- [x] Extend `MCPAgent.__init__` to accept and persist a normalized `user_id`, calling `init_registry(user_id)` during construction (`mcp_agent/mcp_agent.py` now stores `self.user_id`).
- [x] Replace the singleton `_current` with `_current_by_user` mapping; update `set_current`/`current` to read/write agents keyed by normalized `user_id`, instantiating on demand (see `_normalize_user_id` helper in `mcp_agent/mcp_agent.py`). Tests reset the map instead of a single pointer.
- [x] Thread `user_id` through planners, orchestrators, and actions: planner direct-tool calls now pass `context.user_id`, sandbox glue resolves `TB_USER_ID`, `_invoke_mcp_tool`/wrapper auth checks resolve the same env-scoped user, and `OAuthManager.is_authorized` is invoked with that ID (`mcp_agent/planner/actions.py`, `mcp_agent/sandbox/glue.py`, `mcp_agent/actions.py`).
- [x] Ensure logging/metrics include `user_id` so concurrent calls can be diagnosed: `_emit_action_event` attaches it to wrapper telemetry, unauthorized emits add it, and `MCPAgent.call_tool` events (`mcp.call.*`) plus response history entries now carry `user_id`.

## 3. Multi-tenant MCP registry
- [x] Introduce `MCP_BY_USER`, `_REGISTRY_VERSION_BY_USER`, and helpers (`_normalize_user_id`, `_get_bucket`, `get_client`, `registry_version`) in `mcp_agent/registry.py`, keeping `MCP` as the singleton alias for backwards compatibility.
- [x] Update `init_registry(user_id)` to operate on per-user buckets, rebuild providers in-place, honor fake factories/env fallbacks, and bump `_REGISTRY_VERSION_BY_USER` only when the snapshot changes (`mcp_agent/registry.py`).
- [x] Refactor registry consumers to pass `user_id`: `MCPAgent.call_tool` now uses `get_client(..., self.user_id)`, ToolboxBuilder/discovery cache against per-user registry versions, sandbox/toolbox tests patch the new signatures, and planner integration tests align their stubs with the tenant-aware registry.
- [x] Add regression coverage for per-user isolation plus update existing tests to assert user-scoped behavior (`tests/mcp_core/test_registry.py` new `test_registry_isolated_per_user`, toolbox/discovery fixtures updated) and keep integration tests passing.

## 4. Sandbox + env propagation
- [x] In `sandbox/runner.run_python_plan`, set `env["TB_USER_ID"] = user_id` so subprocesses inherit tenant identity (see `mcp_agent/sandbox/runner.py:68-105`). The spawned process now receives the user scope alongside `PYTHONPATH`, ensuring every sandbox invocation mirrors the planner’s tenant.
- [x] Modify `sandbox/glue.register_default_tool_caller` (and async caller helpers) to read `TB_USER_ID` (defaulting to `singleton`) when resolving `MCPAgent.current` (`mcp_agent/sandbox/glue.py:10-45`). This keeps sandbox tool calls aligned with the subprocess env without extra plumbing.
- [x] Update `_invoke_mcp_tool` (and synchronous wrappers) to prefer the env-sourced `TB_USER_ID`, guaranteeing consistent tenant resolution across threads/processes (`mcp_agent/actions.py:18-220`). Unauthorized telemetry and action events now include the scoped `user_id`.
- [x] Add an integration-style test that runs sandbox plans for two distinct `user_id`s and asserts the env separation via returned payloads (`tests/sandbox/test_runner.py:53-72`). This protects against regressions where subprocesses might reuse stale tenant context.

## 5. Planner runtime & command hygiene
- [x] Harden `planner.parser.parse_planner_command` with per-command validation (provider/tool presence, payload dicts, sandbox code, search query/limits, finish summary typing) so malformed LLM outputs raise precise errors, with new tests covering these paths.
- [x] `call_direct_tool` and `run_sandbox_plan` now write structured entries (`tool.<provider>.<tool>`, `sandbox.<label>`) into `context.raw_outputs`, and `_execute_sandbox` honors optional labels; e2e/unit tests assert the new schemas. `run_sandbox_plan` also logs label context and persists sandbox summaries itself.
- [x] `execute_mcp_task` normalizes the returned `MCPTaskResult`, ensuring every response includes `success`, `final_summary`, `raw_outputs`, `budget_usage`, `logs`, and `error` (if any), while existing `_failure`/`_budget_failure` paths feed consistent data.
- [x] Each `PlannerContext` now instantiates its own `TokenCostTracker`, preventing shared global token state between tenants/tests; planner LLM + runtime tests verify the scoped tracker can still be stubbed.

## 6. Concurrency safeguards
- [x] Guard shared registries/manifests with `RLock`s: `mcp_agent/registry.py:5-143` now wraps all MCP registry mutations/readers, `_install_fake_clients`, and version tracking inside `_REGISTRY_LOCK`, while the toolbox manifest cache uses `_MANIFEST_CACHE_LOCK` to protect reads/writes (`mcp_agent/toolbox/builder.py:1-365`).
- [x] Added `MCPClient.acall()` so async callers can await tool invocations without juggling event loops, plus a regression test to ensure it delegates correctly (`mcp_agent/mcp_client.py:1-92`, `tests/mcp_core/test_mcp_client.py:1-18`).
- [x] Audited global state: MCP action telemetry, sandbox events, and registry locks now all carry/guard `user_id`, and no additional mutable singletons exist beyond the newly locked structures (confirmed in `mcp_agent/actions.py`, `mcp_agent/mcp_agent.py`, and `shared.streaming` usage), so no further changes were required.
- [x] Added a threaded stress test (`tests/planner/test_concurrency.py`) that fires `execute_mcp_task` for multiple users in parallel, asserting each result only contains its own tool outputs, proving the planner runtime is safe under concurrent, multi-tenant workloads.

## 7. Delivery & verification sequencing
- [x] Follow the incremental rollout: sections 1–6 of this plan were completed in order (noted above), so each PR-sized unit landed independently before starting the next.
- [x] After each phase, run targeted unit/integration suites (actions, planner, sandbox); latest runs include `pytest tests/mcp_core/test_actions.py tests/planner/test_integration_e2e.py`, `pytest tests/planner tests/sandbox`, and `pytest tests/mcp_core/test_mcp_client.py tests/planner tests/sandbox`, with summaries captured in the CLI output.
- [x] Document migration considerations for deploys: README now has a “Migration notes” section covering the structured action-return contract, `TB_USER_ID` expectations, and multi-tenant scoping requirements (`README.md`).
